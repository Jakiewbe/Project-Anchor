"""Atomic replacement, OS locks and explicit recoverable multi-file transactions."""
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time


class KitError(Exception):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode_json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeError) as exc:
        raise KitError(f"文件损坏或不是 UTF-8 JSON: {path}") from exc


def safe_path(path, root):
    path, root = Path(path), Path(root).resolve()
    for candidate in (path, *path.parents):
        if candidate == root.parent:
            break
        if candidate.exists() or candidate.is_symlink():
            stat = candidate.lstat()
            if candidate.is_symlink() or getattr(stat, "st_file_attributes", 0) & 0x400:
                raise KitError(f"拒绝操作链接或重解析路径: {candidate}")
        if candidate == root:
            break
    if not path.resolve().is_relative_to(root):
        raise KitError(f"路径超出管理范围: {path}")
    return path


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise KitError(f"拒绝覆盖链接文件: {path}")
    fd, name = tempfile.mkstemp(prefix=".kit-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def locked(path, timeout=5):
    """Persistent lock file, released by the OS even when a process crashes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise KitError("锁文件不能是链接")
    with path.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        end = time.monotonic() + timeout
        while True:
            try:
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= end:
                    raise KitError("其他进程正在写入，锁等待超时")
                time.sleep(0.05)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def raw(path):
    return path.read_bytes() if path.exists() else None


def _pack(data):
    return None if data is None else base64.b64encode(data).decode("ascii")


def _unpack(data):
    return None if data is None else base64.b64decode(data, validate=True)


def _put(path, data):
    if data is None:
        path.unlink(missing_ok=True)
    else:
        atomic_write(path, data)


def check_pending(journal):
    if Path(journal).exists():
        raise KitError(f"有未完成的写入。先检查并执行 recover: {journal}")


def transaction(root, journal, updates, expected=None):
    """Caller holds lock. Roll back ordinary errors; journal survives a hard crash."""
    root, journal = Path(root).resolve(), Path(journal)
    check_pending(journal)
    entries = []
    for path, new in updates.items():
        path = safe_path(path, root)
        old = raw(path)
        if expected is not None and path in expected and old != expected[path]:
            raise KitError(f"文件在准备写入期间发生修改: {path}")
        if old != new:
            entries.append({"path": path.relative_to(root).as_posix(),
                            "old": _pack(old), "new": _pack(new)})
    if not entries:
        return
    atomic_write(journal, encode_json({"schema": 1, "entries": entries}))
    try:
        for entry in entries:
            path = safe_path(root / entry["path"], root)
            if raw(path) != _unpack(entry["old"]):
                raise KitError(f"写入期间文件被外部修改: {path}")
            _put(path, _unpack(entry["new"]))
    except Exception:
        # Never overwrite an unrelated external edit during rollback.
        for entry in reversed(entries):
            path = safe_path(root / entry["path"], root)
            current = raw(path)
            if current not in (_unpack(entry["old"]), _unpack(entry["new"])):
                raise KitError("回滚冲突，保留事务记录供 recover 检查")
            if current != _unpack(entry["old"]):
                _put(path, _unpack(entry["old"]))
        journal.unlink()
        raise
    journal.unlink()


def recover(root, journal, rollback=False):
    """Explicit recovery, no guessing which user edits to retain."""
    root, journal = Path(root).resolve(), Path(journal)
    value = read_json(journal)
    if not isinstance(value, dict) or value.get("schema") != 1 or not isinstance(value.get("entries"), list):
        raise KitError("事务记录损坏")
    prepared = []
    try:
        for entry in value["entries"]:
            path = safe_path(root / entry["path"], root)
            old, new = _unpack(entry["old"]), _unpack(entry["new"])
            if raw(path) not in (old, new):
                raise KitError(f"恢复冲突，保留用户修改: {path}")
            prepared.append((path, old if rollback else new))
    except (KeyError, ValueError, TypeError) as exc:
        raise KitError("事务记录损坏") from exc
    for path, data in prepared:
        _put(path, data)
    journal.unlink()
