"""Small, recoverable file transactions for planning workspaces.

Callers hold WorkspaceLock while committing or recovering. Multiple renames are
not an atomic snapshot: a persistent marker makes incomplete writes detectable.
Readers should report pending_transaction(), rather than consume a partial pair.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
from typing import Callable

LOCK_NAME = ".plan-your-project.lock"
TRANSACTION_NAME = ".plan-your-project-transaction"


class WorkspaceIOError(ValueError):
    """A workspace write cannot safely proceed."""


class ConflictError(WorkspaceIOError):
    """The caller's read snapshot is no longer current."""


class PendingTransactionError(WorkspaceIOError):
    """An earlier transaction needs explicit recovery."""


def ensure_within(root: Path, path: Path) -> Path:
    """Resolve a normal file target within root; reject links and special files.

    Parent links are allowed only when their resolved destination stays in root.
    The target itself must be absent or a regular, non-symlink file.
    """
    root = Path(root).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    if candidate.is_symlink():
        raise WorkspaceIOError(f"target must not be a symbolic link: {candidate}")
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root)
    except (ValueError, OSError, RuntimeError) as exc:
        raise WorkspaceIOError(f"path escapes workspace or cannot be resolved: {candidate}") from exc
    if resolved == root:
        raise WorkspaceIOError("workspace root is not a file target")
    if root.exists() and not root.is_dir():
        raise WorkspaceIOError(f"workspace root is not a directory: {root}")
    if resolved.exists() and not stat.S_ISREG(resolved.stat().st_mode):
        raise WorkspaceIOError(f"target is not a regular file: {resolved}")
    for parent in resolved.parents:
        if parent == root:
            break
        if parent.exists() and not parent.is_dir():
            raise WorkspaceIOError(f"target parent is not a directory: {parent}")
    return resolved


def hash_file(path: Path) -> str | None:
    """Return SHA-256 of a regular file, or None when absent."""
    path = Path(path)
    if path.is_symlink():
        raise WorkspaceIOError(f"cannot hash a symbolic-link target: {path}")
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(mode):
        raise WorkspaceIOError(f"cannot hash a non-regular file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


class WorkspaceLock:
    """Short, nonblocking OS advisory lock shared by cooperating writers.

    The small lock file persists; closing the file releases the OS lock even if
    the process exits. A lock is not a substitute for the expected-hash check.
    """
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.fd: int | None = None

    def __enter__(self):
        path = ensure_within(self.root, self.root / LOCK_NAME)
        self.root.mkdir(parents=True, exist_ok=True)
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise WorkspaceIOError("workspace lock is not a regular file")
            if os.name == "nt":
                import msvcrt
                if os.fstat(fd).st_size == 0:
                    os.write(fd, b"\0")
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException as exc:
            os.close(fd)
            if isinstance(exc, OSError):
                raise WorkspaceIOError("workspace is locked by another writer") from exc
            raise
        self.fd = fd
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.fd is not None:
            try:
                if os.name == "nt":
                    import msvcrt
                    os.lseek(self.fd, 0, os.SEEK_SET)
                    msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.fd, fcntl.LOCK_UN)
            finally:
                os.close(self.fd)
                self.fd = None


def pending_transaction(root: Path) -> bool:
    path = Path(root).resolve() / TRANSACTION_NAME
    return path.exists() or path.is_symlink()


def _sync_dir(path: Path) -> None:
    if os.name == "nt":
        return
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_bytes(path: Path, content: bytes, mode: int = 0o600) -> None:
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(path, mode)


def _replace(source: Path, destination: Path) -> None:
    source.replace(destination)


def _write_manifest(tx: Path, manifest: dict) -> None:
    temp = tx / "manifest.json.tmp"
    if temp.exists():
        temp.unlink()
    _write_bytes(temp, (json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    temp.replace(tx / "manifest.json")
    _sync_dir(tx)


def _transaction_dir(root: Path) -> Path:
    tx = root / TRANSACTION_NAME
    if tx.is_symlink() or (tx.exists() and not tx.is_dir()):
        raise WorkspaceIOError("transaction marker must be a regular directory; recovery refused")
    return tx


def _cleanup(root: Path, tx: Path) -> None:
    # No target file is stored beneath this private transaction directory.
    shutil.rmtree(tx)
    _sync_dir(root)


def _read_manifest(root: Path, tx: Path) -> dict | None:
    path = tx / "manifest.json"
    if not path.exists():
        # Preparation never changes destinations before publishing the manifest.
        for item in tx.iterdir():
            if item.is_symlink() or not item.is_file() or not re.fullmatch(r"(?:[0-9]+\.(?:bak|tmp)|manifest\.json\.tmp)", item.name):
                raise WorkspaceIOError("unrecognized incomplete transaction; preserve it for manual recovery")
        return None
    if path.is_symlink() or not path.is_file():
        raise WorkspaceIOError("invalid transaction manifest file")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkspaceIOError("invalid transaction manifest; backups retained") from exc
    if not isinstance(manifest, dict) or manifest.get("version") != 1 or manifest.get("state") not in ("prepared", "committed") or not isinstance(manifest.get("entries"), list) or not manifest["entries"]:
        raise WorkspaceIOError("invalid transaction manifest; backups retained")
    targets = set()
    for index, entry in enumerate(manifest["entries"]):
        if not isinstance(entry, dict) or set(entry) != {"path", "old_hash", "new_hash", "mode", "backup", "staged"}:
            raise WorkspaceIOError("invalid transaction entry; backups retained")
        relative = entry["path"]
        if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise WorkspaceIOError("invalid transaction target; backups retained")
        target = ensure_within(root, root / relative)
        if target.relative_to(root).parts[0] in (LOCK_NAME, TRANSACTION_NAME) or target in targets:
            raise WorkspaceIOError("invalid or repeated transaction target")
        targets.add(target)
        if entry["backup"] != f"{index}.bak" or entry["staged"] != f"{index}.tmp":
            raise WorkspaceIOError("invalid transaction backup names")
        if not isinstance(entry["mode"], int) or not 0 <= entry["mode"] <= 0o7777:
            raise WorkspaceIOError("invalid transaction file mode")
        for key in ("old_hash", "new_hash"):
            digest = entry[key]
            if key == "old_hash" and digest is None:
                continue
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise WorkspaceIOError("invalid transaction content hash")
    return manifest


def _recover(root: Path, replace: Callable[[Path, Path], None]) -> bool:
    root = Path(root).resolve()
    tx = _transaction_dir(root)
    if not tx.exists():
        return False
    manifest = _read_manifest(root, tx)
    if manifest is None:
        _cleanup(root, tx)
        return True
    entries = manifest["entries"]
    # Preflight every destination before restoring any: never overwrite changes
    # made outside this transaction, and do not consume the original backups.
    for entry in entries:
        target = ensure_within(root, root / entry["path"])
        actual = hash_file(target)
        allowed = {entry["new_hash"]} if manifest["state"] == "committed" else {entry["old_hash"], entry["new_hash"]}
        if actual not in allowed:
            raise ConflictError(f"recovery found an independently changed target; backups retained: {entry['path']}")
        if manifest["state"] == "prepared" and entry["old_hash"] is not None:
            if hash_file(tx / entry["backup"]) != entry["old_hash"]:
                raise WorkspaceIOError(f"recovery backup missing or corrupt: {entry['path']}")
    if manifest["state"] == "prepared":
        for index, entry in enumerate(entries):
            target = ensure_within(root, root / entry["path"])
            if hash_file(target) == entry["old_hash"]:
                continue
            if entry["old_hash"] is None:
                target.unlink()
            else:
                temp = tx / f"{index}.restore.tmp"
                if temp.exists():
                    temp.unlink()
                _write_bytes(temp, (tx / entry["backup"]).read_bytes(), entry["mode"])
                replace(temp, target)
            _sync_dir(target.parent)
    _cleanup(root, tx)
    return True


def recover(root: Path) -> bool:
    """Under the caller's lock, roll back a prepared transaction.

    A committed marker only needs cleanup. Modified destinations or corrupt
    backups cause refusal; recovery never silently overwrites new user changes.
    """
    return _recover(root, _replace)


def commit_files(
    root: Path,
    files: dict[Path, str],
    expected: dict[Path, str | None],
    validate: Callable[[], None] | None = None,
) -> None:
    """Commit under the caller's lock, with compare-before-write and recovery.

    Every write target needs an expected hash (None asserts absence). Additional
    expected paths may protect read dependencies such as an unchanged PLAN.
    validate runs against the committed files before backups are removed.
    """
    _commit_files(root, files, expected, validate, _replace)


def _commit_files(
    root: Path,
    files: dict[Path, str],
    expected: dict[Path, str | None],
    validate: Callable[[], None] | None,
    replace: Callable[[Path, Path], None],
) -> None:
    root = Path(root).resolve()
    if pending_transaction(root):
        raise PendingTransactionError("unfinished workspace transaction; run explicit recovery before writing")
    normalized: dict[Path, bytes] = {}
    for path, text in files.items():
        target = ensure_within(root, path)
        if target in normalized:
            raise WorkspaceIOError("multiple write paths resolve to the same target")
        if target.relative_to(root).parts[0] in (LOCK_NAME, TRANSACTION_NAME):
            raise WorkspaceIOError("workspace runtime files cannot be transaction targets")
        if not isinstance(text, str):
            raise WorkspaceIOError("transaction content must be UTF-8 text")
        normalized[target] = text.encode("utf-8")
    conditions = {}
    for path, digest in expected.items():
        target = ensure_within(root, path)
        if target in conditions and conditions[target] != digest:
            raise WorkspaceIOError("inconsistent expected hashes for one target")
        conditions[target] = digest
    if not normalized or not normalized.keys() <= conditions.keys():
        raise WorkspaceIOError("every write target requires an expected hash")
    for path, digest in conditions.items():
        if hash_file(path) != digest:
            raise ConflictError(f"workspace changed since it was read: {path.relative_to(root)}")

    root.mkdir(parents=True, exist_ok=True)
    tx = _transaction_dir(root)
    tx.mkdir(mode=0o700)
    _sync_dir(root)
    manifest = {"version": 1, "state": "prepared", "entries": []}
    committed = False
    try:
        for index, (path, content) in enumerate(normalized.items()):
            mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
            entry = {"path": path.relative_to(root).as_posix(), "old_hash": conditions[path], "new_hash": hashlib.sha256(content).hexdigest(), "mode": mode, "backup": f"{index}.bak", "staged": f"{index}.tmp"}
            if conditions[path] is not None:
                _write_bytes(tx / entry["backup"], path.read_bytes(), mode)
                if hash_file(tx / entry["backup"]) != conditions[path]:
                    raise ConflictError(f"workspace changed during backup: {entry['path']}")
            _write_bytes(tx / entry["staged"], content, mode)
            manifest["entries"].append(entry)
        _write_manifest(tx, manifest)
        for path, digest in conditions.items():
            if hash_file(ensure_within(root, path)) != digest:
                raise ConflictError(f"workspace changed during preparation: {path.relative_to(root)}")
        for entry in manifest["entries"]:
            target = ensure_within(root, root / entry["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            replace(tx / entry["staged"], target)
            _sync_dir(target.parent)
        if validate is not None:
            validate()
        manifest["state"] = "committed"
        _write_manifest(tx, manifest)
        committed = True
    except BaseException as exc:
        try:
            _recover(root, replace)
        except BaseException as recovery_exc:
            raise WorkspaceIOError(f"workspace commit failed; recovery required and backups retained in {tx}: {recovery_exc}") from exc
        raise
    finally:
        if committed:
            # A cleanup failure leaves a committed marker; recover can finish it
            # without undoing a validated transaction.
            _cleanup(root, tx)
