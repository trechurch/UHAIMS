"""
progress_tracker.py — Lightweight background-process progress bus
v1.0.0

Write side (background scripts):
    tracker = ProgressTracker("gl_import", total=9830, label="GL Master Import")
    tracker.update(i + 1, f"Adding {item['description'][:30]}…")
    tracker.done("Import complete — 9,830 items added")

Read side (Streamlit UI):
    from progress_tracker import read_progress, list_active_tasks

Progress files live in /tmp/uha_progress/ as lightweight JSON blobs.
Stale files (not updated for > 90s and not marked finished) are treated as dead.
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional

_DIR = Path("/tmp/uha_progress")
_DIR.mkdir(parents=True, exist_ok=True)

_STALE_SECS = 90   # seconds without an update before a running task is "stalled"


def _path(task_id: str) -> Path:
    return _DIR / f"{task_id}.json"


# ──────────────────────────────────────────────────────────────────────────────
#  Write side
# ──────────────────────────────────────────────────────────────────────────────

class ProgressTracker:
    """
    Attach to any long-running operation (background script or in-process loop)
    and write progress updates that the Streamlit UI can poll.
    """

    def __init__(self, task_id: str, total: int, label: str = "",
                 write_every: int = 1) -> None:
        """
        task_id     — unique identifier, e.g. "gl_import" or "match_engine"
        total       — total number of steps / items
        label       — human-readable task name shown in the UI
        write_every — only write to disk every N calls to update() (reduces I/O)
        """
        self.task_id     = task_id
        self.total       = max(total, 1)
        self.label       = label
        self.write_every = max(write_every, 1)
        self._start      = time.time()
        self._call_count = 0
        self._write(0, "Starting…")

    # ── Public API ────────────────────────────────────────────────────────────

    def update(self, done: int, status: str = "") -> None:
        """Call after each completed step. Throttled by write_every."""
        self._call_count += 1
        if self._call_count % self.write_every == 0 or done >= self.total:
            self._write(done, status)

    def done(self, msg: str = "Complete") -> None:
        """Mark as finished successfully."""
        self._write(self.total, msg, finished=True)

    def error(self, msg: str) -> None:
        """Mark as finished with an error."""
        self._write(self.total, f"ERROR: {msg}", finished=True, errored=True)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _write(self, done: int, status: str,
               finished: bool = False, errored: bool = False) -> None:
        elapsed = time.time() - self._start
        pct     = done / self.total
        if pct > 0.01 and not finished and elapsed > 0.5:
            rate = done / elapsed          # items/sec
            eta  = (self.total - done) / rate if rate > 0 else None
        else:
            eta = None

        payload = {
            "task_id":    self.task_id,
            "label":      self.label,
            "total":      self.total,
            "done":       done,
            "pct":        round(pct, 5),
            "elapsed":    round(elapsed, 1),
            "eta":        round(eta, 0) if eta is not None else None,
            "status":     status,
            "finished":   finished,
            "errored":    errored,
            "updated_at": time.time(),
        }
        try:
            _path(self.task_id).write_text(json.dumps(payload))
        except Exception:
            pass   # never crash the caller over a progress write


# ──────────────────────────────────────────────────────────────────────────────
#  Read side
# ──────────────────────────────────────────────────────────────────────────────

def read_progress(task_id: str) -> Optional[Dict]:
    """
    Read progress for a specific task.
    Returns None if the file doesn't exist.
    Annotates stale records with stalled=True.
    """
    try:
        p = _path(task_id)
        if not p.exists():
            return None
        data = json.loads(p.read_text())
        _annotate_stale(data)
        return data
    except Exception:
        return None


def list_active_tasks() -> List[Dict]:
    """Return all non-finished tasks, sorted by most recently updated."""
    results = []
    try:
        for f in sorted(_DIR.glob("*.json"),
                        key=lambda f: f.stat().st_mtime, reverse=True):
            try:
                data = json.loads(f.read_text())
                if not data.get("finished"):
                    _annotate_stale(data)
                    results.append(data)
            except Exception:
                pass
    except Exception:
        pass
    return results


def list_recent_tasks(limit: int = 10) -> List[Dict]:
    """All tasks (including finished), most recent first."""
    results = []
    try:
        for f in sorted(_DIR.glob("*.json"),
                        key=lambda f: f.stat().st_mtime, reverse=True)[:limit]:
            try:
                data = json.loads(f.read_text())
                _annotate_stale(data)
                results.append(data)
            except Exception:
                pass
    except Exception:
        pass
    return results


def clear_progress(task_id: str) -> None:
    """Delete a specific progress file."""
    try:
        _path(task_id).unlink(missing_ok=True)
    except Exception:
        pass


def clear_all_finished() -> int:
    """Delete all finished (or stale) progress files. Returns count removed."""
    removed = 0
    try:
        for f in _DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                _annotate_stale(data)
                if data.get("finished") or data.get("stalled"):
                    f.unlink()
                    removed += 1
            except Exception:
                pass
    except Exception:
        pass
    return removed


def _annotate_stale(data: Dict) -> None:
    """Mutate data in place: add stalled=True if running but not updated recently."""
    if not data.get("finished"):
        age = time.time() - data.get("updated_at", 0)
        if age > _STALE_SECS:
            data["stalled"] = True
            data["status"]  = (f"No update for {int(age)}s — "
                               f"process may have finished or stalled")
