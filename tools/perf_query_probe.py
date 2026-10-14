"""Reversible programmatic StringVar probe; no native imports or artifact IO."""

_MISSING = object()


class QueryProbe:
    def __init__(self, app, mode, rules, *, clock, schedule, geometry_check, done):
        from tools.perf_query import query_plan
        self.app, self.mode, self.rules = app, mode, rules
        self.clock, self.schedule, self.geometry_check, self.done = clock, schedule, geometry_check, done
        self.plan = query_plan(mode)
        self.writes, self.renders, self.timers, self.saved = [], [], {}, {}
        self.active_write = self.callback_write = None
        self.active = self.finished = False
        self.deadline_ns = None

    def guard(self):
        if not self.active or self.app.closed or self.app.closing:
            return False
        if self.clock() >= self.deadline_ns:
            raise RuntimeError("query sequence deadline exhausted")
        return True

    def start(self):
        self.active = True
        self.deadline_ns = self.clock() + 30_000_000_000
        for name in ("after", "after_cancel", "render_rules"):
            self.saved[name] = (self.app.__dict__.get(name, _MISSING), getattr(self.app, name))
        self.app.after, self.app.after_cancel, self.app.render_rules = self.after, self.cancel, self.render
        self.schedule(self.timeout, deadline_ns=self.deadline_ns, timeout_reason="query timeout")
        self.schedule(lambda: self.write(0))

    def timeout(self):
        raise RuntimeError("query sequence timeout")

    def close(self):
        self.active = False
        for name, (raw, _) in self.saved.items():
            if raw is _MISSING:
                self.app.__dict__.pop(name, None)
            else:
                setattr(self.app, name, raw)
        self.saved.clear()

    def write(self, index):
        if not self.guard():
            return
        self.geometry_check()
        if not self.guard():
            return
        step = self.plan[index]
        row = dict(seq=index + 1, query=step.query, begin_ns=self.clock(), set_return_ns=None,
                   revision=None, ticket=None, timer_id=None, schedule_begin_ns=None,
                   schedule_return_ns=None, delay_ms=None, callback_enter_ns=None,
                   cancelled_ns=None, requested_gap_ms=step.delay_ms)
        self.writes.append(row)
        self.active_write = row
        try:
            self.app.rule_search.set(step.query)
            row["set_return_ns"] = self.clock()
        finally:
            self.active_write = None
        if not self.guard():
            return
        actual_query = self.app.rule_search.get()
        if not self.guard():
            return
        if (row["timer_id"] is None or row["timer_id"] != self.app.rule_search_timer
                or row["revision"] != self.app.rule_search_revision
                or row["ticket"] != self.app.rule_search_ticket
                or actual_query != step.query):
            raise RuntimeError("query debounce registration missing or ambiguous")
        if index + 1 < len(self.plan):
            self.schedule(lambda: self.write(index + 1), delay=self.plan[index + 1].delay_ms)

    def after(self, delay, callback=None, *args):
        original = self.saved["after"][1]
        row = self.active_write
        if row is None or delay != 200 or callback is None:
            return original(delay, callback, *args)
        if row["timer_id"] is not None:
            raise RuntimeError("multiple debounce registrations inside one write")
        row.update(schedule_begin_ns=self.clock(), delay_ms=delay,
                   revision=self.app.rule_search_revision, ticket=self.app.rule_search_ticket)
        def invoke(*values):
            # Plain attributes and cancellation state precede any Tcl getter.
            if (not self.active or self.app.closed or self.app.closing
                    or row["cancelled_ns"] is not None
                    or row["ticket"] != self.app.rule_search_ticket):
                return
            if row["callback_enter_ns"] is not None:
                return
            row["callback_enter_ns"] = self.clock()
            self.callback_write = row
            try:
                return callback(*values)
            finally:
                self.callback_write = None
        handle = original(delay, invoke, *args)
        row.update(schedule_return_ns=self.clock(), timer_id=handle)
        self.timers[handle] = row
        return handle

    def cancel(self, handle):
        result = self.saved["after_cancel"][1](handle)
        row = self.timers.get(handle)
        if row is not None and row["callback_enter_ns"] is None:
            row["cancelled_ns"] = self.clock()
        return result

    def render(self, *args, **kwargs):
        if not self.guard():
            return
        row = self.callback_write
        if row is None:
            raise RuntimeError("untracked render during query sequence")
        query = self.app.rule_search.get()
        if not self.guard():
            return
        revision = self.app.rule_search_revision
        if query != row["query"] or revision != row["revision"]:
            raise RuntimeError("query render belongs to another revision")
        self.geometry_check()
        if not self.guard():
            return
        item = dict(write_seq=row["seq"], revision=revision, query=query,
                    ticket_original=row["ticket"], start_ns=self.clock(), return_ns=None,
                    observation_ns=None, settled=False, pending=None, timer_id=None,
                    full_indices=None, rows=None, page=None, page_count=None)
        self.renders.append(item)
        result = self.saved["render_rules"][1](*args, **kwargs)
        item["return_ns"] = self.clock()
        if not self.guard():
            return result
        self.geometry_check()
        if not self.guard():
            return result
        context = self.app.rule_view_context
        item.update(full_indices=list(context[2]),
                    rows=sum(field != "windows" for field, _ in self.app.review_rows),
                    page=self.app.rule_page_result.page if self.app.rule_page_result else None,
                    page_count=self.app.rule_page_result.page_count if self.app.rule_page_result else None)
        deadline = min(self.deadline_ns, item["return_ns"] + 10_000_000_000)
        item["deadline_ns"] = deadline
        self.schedule(lambda: self.observation_timeout(item), deadline_ns=deadline,
                      timeout_reason="query observation timeout")
        self.schedule(lambda: self.observed(item, context), idle=True,
                      deadline_ns=deadline, timeout_reason="query observation timeout")
        return result

    def observation_timeout(self, item):
        if self.active and item["observation_ns"] is None:
            raise RuntimeError("query observation timeout")

    def observed(self, item, context):
        if not self.guard():
            return
        if self.clock() >= item["deadline_ns"]:
            raise RuntimeError("query observation deadline exhausted")
        self.geometry_check()
        if not self.guard():
            return
        current_query = (self.app.rule_search.get() if self.app.rule_search_revision == item["revision"] else None)
        if not self.guard():
            return
        item.update(pending=self.app.rule_search_pending, timer_id=self.app.rule_search_timer,
                    settled=(self.app.rule_search_revision == item["revision"]
                             and current_query == item["query"]
                             and not self.app.rule_search_pending and self.app.rule_search_timer is None
                             and self.app.rule_view_context is context))
        item["observation_ns"] = self.clock()
        if item["observation_ns"] >= item["deadline_ns"]:
            raise RuntimeError("query observation deadline exhausted")
        if item["settled"] and item["write_seq"] == len(self.plan) and len(self.writes) == len(self.plan):
            self.finished = True
            self.close()
            self.done(self)

    def packet(self):
        return dict(query_schema_version=1, mode=self.mode, writes=self.writes, renders=self.renders,
                    status="complete" if self.finished else "partial")
