import json
import os
from datetime import datetime, timezone

from app.config import LOCK_FILE


class CollectorAlreadyRunning(RuntimeError):
    """Raised when another scraper process holds the browser profile lock."""


class CollectorLock:
    """Small cross-platform lock to avoid two collectors sharing one profile."""

    def __init__(self, path=LOCK_FILE):
        self.path = path
        self._file = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.release()

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.path, "a+", encoding="utf-8")

        try:
            self._lock_file()
        except OSError as exc:
            details = self._read_existing_details()
            self._file.close()
            self._file = None
            raise CollectorAlreadyRunning(details) from exc

        self._file.seek(0)
        self._file.truncate()
        json.dump(
            {
                "pid": os.getpid(),
                "started_at": datetime.now(timezone.utc).isoformat(),
                "cwd": os.getcwd(),
            },
            self._file,
            ensure_ascii=False,
        )
        self._file.flush()
        os.fsync(self._file.fileno())

    def release(self):
        if not self._file:
            return
        try:
            self._unlock_file()
        finally:
            self._file.close()
            self._file = None
        try:
            self.path.unlink()
        except OSError:
            pass

    def _read_existing_details(self):
        try:
            self._file.seek(0)
            return self._file.read().strip()
        except OSError:
            return str(self.path)

    def _lock_file(self):
        self._file.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock_file(self):
        self._file.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
