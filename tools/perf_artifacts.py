"""Exclusive QA artifacts; no GUI, controller or user configuration access.

Writes are confined to an existing run-<UUID> directory below a workspace's
.qa. Paths are checked before IO; this is not an adversarial filesystem lock.
Publication is atomic and never replaces an existing destination.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from uuid import uuid4


_RUN_NAME = re.compile(r"run-[0-9a-f]{32}\Z")


def _absolute(path):
    path = Path(path)
    if ".." in path.parts:
        raise ValueError("Parent traversal is not allowed in QA paths")
    return Path(os.path.abspath(path))


def _check_links(path):
    for component in reversed((path, *path.parents)):
        if component.is_symlink() or component.is_junction():
            raise ValueError(f"QA paths cannot contain links or junctions: {component}")


def _contained(path, qa_root):
    _check_links(path)
    if not path.is_relative_to(qa_root) or not path.resolve().is_relative_to(qa_root.resolve()):
        raise ValueError("Destination must remain inside workspace/.qa")
    for part in path.relative_to(qa_root).parts:
        if ":" in part:
            raise ValueError("Alternate data streams are not QA artifacts")


def create_run(workspace, out_parent=None):
    """Return a new exclusive run directory under workspace/.qa (Path).

    Relative out_parent is relative to workspace. Invalid paths are rejected
    before creating any directory; a UUID collision is an error, not a retry.
    """
    workspace = _absolute(workspace)
    _check_links(workspace)
    if not workspace.is_dir():
        raise ValueError("Workspace must be an existing directory")
    qa_root = workspace / ".qa"
    if out_parent is None:
        parent = qa_root / "performance"
    else:
        parent = Path(out_parent)
        if not parent.is_absolute():
            parent = workspace / parent
        parent = _absolute(parent)
    _contained(parent, qa_root)
    run = parent / f"run-{uuid4().hex}"
    _contained(run, qa_root)
    if os.path.lexists(run):
        raise FileExistsError(f"Run already exists: {run}")
    parent.mkdir(parents=True, exist_ok=True)
    _contained(run, qa_root)
    run.mkdir(exist_ok=False)
    return run


def _artifact_path(path):
    path = _absolute(path)
    qa_root = next((parent for parent in path.parents if parent.name == ".qa"), None)
    if qa_root is None:
        raise ValueError("Artifact must be inside workspace/.qa")
    _contained(path, qa_root)
    run = next((parent for parent in path.parents
                if parent != qa_root and parent.is_relative_to(qa_root)
                and _RUN_NAME.fullmatch(parent.name)), None)
    if run is None or not run.is_dir() or not path.parent.is_dir():
        raise ValueError("Artifact requires an existing run-<UUID> and parent directory")
    if os.path.lexists(path):
        raise FileExistsError(f"Artifact already exists: {path}")
    return path


def _publish(path, contents):
    path = _artifact_path(path)
    fd, temporary = tempfile.mkstemp(prefix=".artifact-", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary)
    try:
        try:
            stream = os.fdopen(fd, "wb")
        except BaseException:
            os.close(fd)
            raise
        with stream:
            if stream.write(contents) != len(contents):
                raise OSError("Incomplete artifact write")
            stream.flush()
            os.fsync(stream.fileno())
        _artifact_path(path)
        if os.name == "nt":
            os.rename(temporary, path)  # Windows rename refuses existing targets.
        else:
            os.link(temporary, path)  # POSIX rename would silently overwrite.
        return path
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path, data):
    """Publish one UTF-8 JSON document with LF terminator; return its Path."""
    contents = (json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")
    return _publish(path, contents)


def write_jsonl(path, records):
    """Publish complete UTF-8 JSONL from a one-shot iterable; return its Path.

    Serialization finishes before IO. Each record has one LF terminator; an
    empty iterable creates an empty file. Nonfinite numbers are rejected.
    """
    contents = b"".join((json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
                        for record in records)
    return _publish(path, contents)


def make_fixture(run_dir, rules):
    """Return config.json containing uniform R_N for N=0, 100 or 1000."""
    if type(rules) is not int or rules not in (0, 100, 1000):
        raise ValueError("rules must be an integer in {0, 100, 1000}")
    return write_json(Path(run_dir) / "config.json", {
        "windows": [],
        "block_exes": [f"qa-{index:04}.exe" for index in range(rules)],
        "block_folders": [],
        "safelist_exes": [],
        "block_cmdline": [],
    })


def file_sha256(path):
    """Return lowercase SHA256 of actual file bytes, also for source files."""
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
