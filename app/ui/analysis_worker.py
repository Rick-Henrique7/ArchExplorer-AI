"""Background worker that runs AI inference in a QThreadPool."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from app.services import AIEngine, AIServiceUnavailableError


class _WorkerSignals(QObject):
    """Companion QObject carrying signals for :class:`AnalysisWorker`.

    ``QRunnable`` is not a ``QObject`` and cannot declare signals directly;
    the standard PySide6 pattern is to keep the signals on a small companion
    QObject that the worker holds a reference to.
    """

    finished = Signal(str)  # result markdown
    failed = Signal(str)    # error message


class AnalysisWorker(QRunnable):
    """Runs :meth:`AIEngine.analyze_architecture` in a background thread.

    Construct with keyword-only arguments, then submit to
    ``QThreadPool.globalInstance().start(worker)``. **Connect to
    ``worker.signals.finished`` and ``worker.signals.failed`` before
    starting the worker** — signal-slot connections across threads work
    automatically (queued connection).
    """

    def __init__(
        self,
        *,
        ai_engine: AIEngine,
        code_content: str,
        file_type: str,
        file_label: str = "",
    ) -> None:
        super().__init__()
        self._engine = ai_engine
        self._code = code_content
        self._file_type = file_type
        self._label = file_label
        self.signals = _WorkerSignals()

    @Slot()
    def run(self) -> None:
        """Entry point invoked by the QThreadPool.

        Emits exactly one of ``signals.finished`` or ``signals.failed``.
        Catches all exceptions to keep the Qt event loop healthy; failures
        are reported via the ``failed`` signal with a user-facing message.
        """
        try:
            result = self._engine.analyze_architecture(self._code, self._file_type)
        except AIServiceUnavailableError as exc:
            self.signals.failed.emit(f"AI service unavailable: {exc.message}")
        except Exception as exc:  # noqa: BLE001 — we want to catch all
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.signals.finished.emit(result)
