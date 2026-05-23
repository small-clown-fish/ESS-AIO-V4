from __future__ import annotations

import queue
import threading
from typing import Any


class AsyncRecorderProxy:
    """Small write queue in front of CsvRecorder / AlarmRecorder.

    UI thread enqueues writes quickly; a background writer flushes to disk.
    close() drains the queue before closing the wrapped recorder.
    """

    def __init__(self, recorder: Any, max_queue: int = 20000) -> None:
        self.recorder = recorder
        self.queue: queue.Queue[tuple[str, tuple[Any, ...], dict[str, Any]] | None] = queue.Queue(maxsize=max_queue)
        self.running = True
        self.dropped_rows = 0
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def write_row(self, *args: Any, **kwargs: Any) -> None:
        if not self.running:
            return
        try:
            self.queue.put_nowait(("write_row", args, kwargs))
        except queue.Full:
            self.dropped_rows += 1

    def _run(self) -> None:
        while True:
            item = self.queue.get()
            if item is None:
                self.queue.task_done()
                break
            method_name, args, kwargs = item
            try:
                getattr(self.recorder, method_name)(*args, **kwargs)
            except Exception:
                # Recorder errors should not crash sampling/UI.
                pass
            finally:
                self.queue.task_done()

    def close(self) -> None:
        if not self.running:
            return
        self.running = False
        self.queue.put(None)
        self.queue.join()
        self.thread.join(timeout=5.0)
        try:
            self.recorder.close()
        except Exception:
            pass

    def __getattr__(self, name: str) -> Any:
        return getattr(self.recorder, name)
