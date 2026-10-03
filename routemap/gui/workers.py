"""
Background work for the window: one QThread per job, results back as signals.

Every network or subprocess call happens here, never on the UI thread, so the
window stays responsive while a 60 second trace runs and the tool's lines can be
shown as they arrive. Each job is a plain function given three callbacks; the
function knows nothing about Qt.
"""
from __future__ import annotations

import threading
import traceback

from PySide6.QtCore import QThread, Signal


class Task(QThread):
    line = Signal(str)                    # one line of tool output
    progress = Signal(str, str, str)      # source, state, detail
    hop = Signal(object)                  # the route so far, after a hop was placed
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, job, parent=None):
        super().__init__(parent)
        self.job = job
        self.cancel = threading.Event()

    def run(self):
        try:
            result = self.job(on_line=self.line.emit,
                              on_progress=lambda s, st, d=None: self.progress.emit(s, st, d or ""),
                              cancel=self.cancel, on_hop=self.hop.emit)
        except Exception as exc:  # noqa: BLE001 - every failure reaches the UI as text
            message = getattr(exc, "message", None) or str(exc) or exc.__class__.__name__
            if not isinstance(exc, (ValueError, RuntimeError, OSError)):
                traceback.print_exc()
            self.failed.emit(message)
            return
        self.succeeded.emit(result)

    def stop(self):
        self.cancel.set()
