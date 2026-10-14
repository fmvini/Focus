"""Pure event validation for programmatic R_N search measurements.

No clock, IO, toolkit, process or configuration imports. All timestamps are
nonnegative integer nanoseconds supplied by the probe. Summaries describe
observed endpoints, not physical keyboard input, pixels or RNF acceptance.
"""

from typing import NamedTuple


class QueryStep(NamedTuple):
    query: str
    delay_ms: int


def query_plan(mode):
    """Return immutable steps; reset is an internal, separate measurement."""
    if type(mode) is not str:
        raise ValueError("mode must be none, single, burst, spaced or reset")
    if mode == "none":
        return ()
    if mode == "reset":
        return (QueryStep("", 0),)
    if mode == "single":
        return (QueryStep("qa-00", 0),)
    if mode in ("burst", "spaced"):
        delay = 50 if mode == "burst" else 500
        return tuple(QueryStep(value, 0 if index == 0 else delay)
                     for index, value in enumerate(("q", "qa", "qa-", "qa-0", "qa-00")))
    raise ValueError("mode must be none, single, burst, spaced or reset")


def _integer(value):
    return type(value) is int and value >= 0


def _difference(end, begin):
    return None if end is None or begin is None or end < begin else end - begin


def summarize_query(writes, renders, mode, rules):
    """Validate records without modifying them; return integer ns or None.

    Result keys: ok/errors/insufficient, mode/rules, expected_writes/counts,
    requested_delays_ms, actual_intervals_ns (begin-to-begin), actual_gaps_ns
    (previous set return to next begin), write_timings/render_timings,
    final_write_seq/revision/query/observation_ns, and
    last_write_to_observation_ns/first_write_to_observation_ns.

    Each write timing contains status, set_call_ns, write_to_callback_ns and
    callback_wait_ns (schedule return to callback). Each render timing contains
    status, callback_to_render_ns, render_call_ns and layout_wait_ns. A cancelled
    final write never wins, even if its callback entered. Intermediate renders
    with no observation may be superseded; no fixed render count is required.
    Input chronology is preserved, never repaired by sorting/deduplication.
    Bad parameters raise ValueError; malformed/partial events remain diagnostics.
    """
    plan = query_plan(mode)
    if type(rules) is not int or rules not in (0, 100, 1000):
        raise ValueError("rules must be 0, 100 or 1000")
    source_writes, source_renders = list(writes), list(renders)
    errors, insufficient = [], []

    def integer(record, field, scope, *, optional=False):
        value = record.get(field)
        if value is None:
            if not optional:
                insufficient.append(f"{scope}: missing {field}")
            return None
        if not _integer(value):
            errors.append(f"{scope}: {field} must be a nonnegative integer")
            return None
        return value

    def text(record, field, scope, *, optional=False):
        value = record.get(field)
        if value is None and optional:
            return None
        if type(value) is not str:
            errors.append(f"{scope}: {field} must be a string")
            return None
        return value

    def check_order(values, scope):
        available = [value for value in values if value is not None]
        if any(right < left for left, right in zip(available, available[1:])):
            errors.append(f"{scope}: timestamps are not chronological")

    if len(source_writes) < len(plan):
        insufficient.append("Query plan has incomplete writes")
    if len(source_writes) > len(plan):
        errors.append("More writes than the query plan")
    if mode == "none" and source_renders:
        errors.append("Disabled query has unexpected renders")

    parsed_writes, by_seq, timer_ids = [], {}, set()
    for index, record in enumerate(source_writes):
        scope = f"write[{index}]"
        initial = len(errors), len(insufficient)
        if not isinstance(record, dict):
            errors.append(f"{scope}: expected a dict")
            parsed_writes.append(None)
            continue
        item = {field: integer(record, field, scope) for field in
                ("seq", "begin_ns", "set_return_ns", "revision", "ticket",
                 "schedule_begin_ns", "schedule_return_ns", "delay_ms")}
        item.update(query=text(record, "query", scope),
                    timer_id=text(record, "timer_id", scope),
                    callback_enter_ns=integer(record, "callback_enter_ns", scope, optional=True),
                    cancelled_ns=integer(record, "cancelled_ns", scope, optional=True))
        if index < len(plan) and item["query"] != plan[index].query:
            errors.append(f"{scope}: query does not match plan")
        if item["delay_ms"] is not None and item["delay_ms"] != 200:
            errors.append(f"{scope}: original debounce must remain 200 ms")
        check_order([item[field] for field in ("begin_ns", "schedule_begin_ns", "schedule_return_ns",
                                             "set_return_ns", "callback_enter_ns")], scope)
        check_order([item["schedule_return_ns"], item["cancelled_ns"]], scope)
        if item["timer_id"] == "":
            errors.append(f"{scope}: timer_id must not be empty")
        elif item["timer_id"] is not None:
            if item["timer_id"] in timer_ids:
                errors.append(f"{scope}: duplicate timer_id")
            timer_ids.add(item["timer_id"])
        previous = next((value for value in reversed(parsed_writes) if value is not None), None)
        if previous is not None:
            check_order([previous["set_return_ns"], item["begin_ns"]], scope)
            for field in ("seq", "revision", "ticket"):
                if (previous[field] is not None and item[field] is not None
                        and item[field] <= previous[field]):
                    errors.append(f"{scope}: {field} must increase")
        if item["seq"] is not None:
            if item["seq"] in by_seq:
                errors.append(f"{scope}: duplicate seq")
            else:
                by_seq[item["seq"]] = item
        item["valid"] = initial == (len(errors), len(insufficient))
        item["last_render_observation_ns"] = None
        parsed_writes.append(item)

    render_timings = []
    previous_return = None
    for index, record in enumerate(source_renders):
        scope = f"render[{index}]"
        initial = len(errors), len(insufficient)
        if not isinstance(record, dict):
            errors.append(f"{scope}: expected a dict")
            render_timings.append({"status": "invalid", "write_seq": None})
            continue
        item = {field: integer(record, field, scope) for field in
                ("write_seq", "revision", "ticket_original", "start_ns", "return_ns")}
        item.update(query=text(record, "query", scope),
                    observation_ns=integer(record, "observation_ns", scope, optional=True))
        check_order([item["start_ns"], item["return_ns"], item["observation_ns"]], scope)
        check_order([previous_return, item["start_ns"]], scope)
        if item["return_ns"] is not None:
            previous_return = item["return_ns"]
        origin = by_seq.get(item["write_seq"])
        if origin is None:
            errors.append(f"{scope}: unknown write_seq")
        else:
            # A previous observation cannot prove the context of a later render.
            origin["last_render_observation_ns"] = None
            for render_field, write_field in (("revision", "revision"), ("query", "query"),
                                             ("ticket_original", "ticket")):
                if item[render_field] != origin[write_field]:
                    errors.append(f"{scope}: {render_field} does not match original write")
            if not origin["valid"]:
                errors.append(f"{scope}: origin write is invalid or incomplete")
            if origin["callback_enter_ns"] is None:
                insufficient.append(f"{scope}: original callback entry is missing")
            check_order([origin["callback_enter_ns"], item["start_ns"]], scope)
            if any(write is not None and write["seq"] is not None and origin["seq"] is not None
                   and write["seq"] > origin["seq"] and write["begin_ns"] is not None
                   and item["start_ns"] is not None and write["begin_ns"] <= item["start_ns"]
                   for write in parsed_writes):
                errors.append(f"{scope}: render started after its write was superseded")
            if (origin["cancelled_ns"] is not None and item["start_ns"] is not None
                    and item["start_ns"] >= origin["cancelled_ns"]):
                errors.append(f"{scope}: render follows cancellation of its callback")

        observed = item["observation_ns"] is not None
        for field in ("settled", "pending"):
            value = record.get(field)
            if type(value) is not bool and not (value is None and not observed):
                errors.append(f"{scope}: {field} must be a boolean at observation")
        if observed and "timer_id" not in record:
            insufficient.append(f"{scope}: observation timer_id is missing")
        timer = record.get("timer_id")
        if timer is not None and (type(timer) is not str or not timer):
            errors.append(f"{scope}: timer_id must be None or a nonempty string")
        settled = observed and record.get("settled") is True
        indices = record.get("full_indices")
        if indices is not None and (type(indices) not in (list, tuple)
                                    or any(not _integer(value) for value in indices)):
            errors.append(f"{scope}: full_indices must be integer positions")
        for field in ("rows", "page", "page_count"):
            if record.get(field) is not None:
                integer(record, field, scope)
        if settled:
            if record.get("pending") is not False or timer is not None:
                errors.append(f"{scope}: settled observation still has pending search/timer")
            if any(write is not None and write["seq"] is not None and item["write_seq"] is not None
                   and write["seq"] > item["write_seq"] and write["begin_ns"] is not None
                   and write["begin_ns"] <= item["observation_ns"]
                   for write in parsed_writes):
                errors.append(f"{scope}: settled observation was superseded by another write")
            count = min(rules, 100) if item["query"] == "qa-00" else rules
            expected = {"rows": min(25, count), "page": 0, "page_count": max(1, (count + 24) // 25)}
            if indices is None:
                insufficient.append(f"{scope}: settled FULL indices are missing")
            elif type(indices) in (tuple, list) and tuple(indices) != tuple(range(count)):
                errors.append(f"{scope}: FULL indices do not match R_N oracle")
            for field, value in expected.items():
                if record.get(field) is None:
                    insufficient.append(f"{scope}: settled {field} is missing")
                elif type(record[field]) is not int or record[field] != value:
                    errors.append(f"{scope}: {field} does not match R_N oracle")
        elif not observed and record.get("settled") is True:
            errors.append(f"{scope}: settled render has no observation")
        valid = initial == (len(errors), len(insufficient))
        status = "settled" if settled else "superseded"
        if not valid:
            status = "invalid"
        elif not settled and (not parsed_writes or origin is parsed_writes[-1]):
            status = "partial"
        timing = dict(write_seq=item["write_seq"], revision=item["revision"], status=status,
                      observation_ns=item["observation_ns"],
                      callback_to_render_ns=_difference(item["start_ns"], origin["callback_enter_ns"] if origin else None),
                      render_call_ns=_difference(item["return_ns"], item["start_ns"]),
                      layout_wait_ns=_difference(item["observation_ns"], item["return_ns"]))
        render_timings.append(timing)
        if valid and settled and origin is not None:
            origin["last_render_observation_ns"] = item["observation_ns"]

    write_timings = []
    actual_intervals, actual_gaps = [], []
    for index, item in enumerate(parsed_writes):
        if item is None:
            write_timings.append({"status": "invalid", "seq": None})
            continue
        status = ("invalid" if not item["valid"] else "cancelled" if item["cancelled_ns"] is not None
                  else "settled" if item["last_render_observation_ns"] is not None
                  else "superseded" if index + 1 < len(parsed_writes)
                  else "partial")
        write_timings.append(dict(seq=item["seq"], query=item["query"], revision=item["revision"], status=status,
                                  set_call_ns=_difference(item["set_return_ns"], item["begin_ns"]),
                                  write_to_callback_ns=_difference(item["callback_enter_ns"], item["begin_ns"]),
                                  callback_wait_ns=_difference(item["callback_enter_ns"], item["schedule_return_ns"])))
    for previous, item in zip(parsed_writes, parsed_writes[1:]):
        actual_intervals.append(_difference(item["begin_ns"] if item else None,
                                            previous["begin_ns"] if previous else None))
        actual_gaps.append(_difference(item["begin_ns"] if item else None,
                                      previous["set_return_ns"] if previous else None))

    last = parsed_writes[-1] if parsed_writes else None
    final = (last["last_render_observation_ns"] if plan and len(source_writes) == len(plan)
             and last is not None and last["valid"] and last["query"] == plan[-1].query
             and last["cancelled_ns"] is None else None)
    if plan and final is None:
        insufficient.append("Final original revision has no settled, uncancelled observation")
    first = parsed_writes[0] if parsed_writes else None
    return {
        "ok": not errors and not insufficient, "errors": errors, "insufficient": insufficient,
        "mode": mode, "rules": rules, "expected_writes": len(plan),
        "writes_count": len(source_writes), "renders_count": len(source_renders),
        "requested_delays_ms": [step.delay_ms for step in plan],
        "actual_intervals_ns": actual_intervals, "actual_gaps_ns": actual_gaps,
        "write_timings": write_timings, "render_timings": render_timings,
        "final_write_seq": last["seq"] if last else None,
        "final_revision": last["revision"] if last else None,
        "final_query": last["query"] if last else None, "final_observation_ns": final,
        "last_write_to_observation_ns": _difference(final, last["begin_ns"] if last else None),
        "first_write_to_observation_ns": _difference(final, first["begin_ns"] if first else None),
    }
