"""Background workers that run AI inference in a QThreadPool.

Three workers live here (all :class:`QRunnable`):

- :class:`AnalysisWorker` — runs ``AIEngine.analyze_architecture`` for a
  file the user clicked in the explorer (Change 003).
- :class:`AIEditWorker` — runs ``AIEngine.edit_file`` for the "Edit
  with AI" flow (Change 005). Returns a new file body; the caller is
  expected to show a preview dialog before writing it to disk.
- :class:`ChatWorker` — runs the provider directly with a free-form
  prompt built by the :class:`VisualizerPanel` (Change 005).

All three follow the same pattern:

- Each holds a small companion :class:`_WorkerSignals` QObject because
  QRunnable is not a QObject and cannot declare signals directly.
- Each ``run()`` catches :class:`AIServiceUnavailableError` and generic
  ``Exception``, emitting ``failed`` so the Qt event loop stays healthy.
- The success path emits ``finished`` with a string payload (markdown,
  new file content, or assistant reply).
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from app.services import AIEngine, AIServiceUnavailableError, SYSTEM_PROMPT


class _WorkerSignals(QObject):
    """Companion QObject carrying signals for all workers.

    ``QRunnable`` is not a ``QObject`` and cannot declare signals directly;
    the standard PySide6 pattern is to keep the signals on a small companion
    QObject that the worker holds a reference to.
    """

    finished = Signal(str)  # result string
    failed = Signal(str)    # error message


class AnalysisWorker(QRunnable):
    """Runs :meth:`AIEngine.analyze_architecture` in a background thread."""

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
        try:
            result = self._engine.analyze_architecture(self._code, self._file_type)
        except AIServiceUnavailableError as exc:
            self.signals.failed.emit(f"AI service unavailable: {exc.message}")
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.signals.finished.emit(result)


class AIEditWorker(QRunnable):
    """Runs :meth:`AIEngine.edit_file` in a background thread.

    Emits ``finished(new_content)`` with the LLM-suggested file body.
    The caller (MainWindow) shows a preview dialog and, on confirm,
    writes the new content to disk via :class:`FileManager`.
    """

    def __init__(
        self,
        *,
        ai_engine: AIEngine,
        current_content: str,
        instruction: str,
        file_type: str,
        file_path: str = "",
    ) -> None:
        super().__init__()
        self._engine = ai_engine
        self._content = current_content
        self._instruction = instruction
        self._file_type = file_type
        self._path = file_path
        self.signals = _WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            new_content = self._engine.edit_file(
                self._content, self._instruction, self._file_type
            )
        except AIServiceUnavailableError as exc:
            self.signals.failed.emit(f"AI service unavailable: {exc.message}")
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.signals.finished.emit(new_content)


class ChatWorker(QRunnable):
    """Runs a free-form chat prompt in a background thread.

    The prompt is fully built by the :class:`VisualizerPanel` (with file
    context + recent history) — this worker is a thin wrapper that
    delegates to the engine's underlying provider with a slightly
    higher temperature (chat feels more natural with a bit of variety).
    """

    def __init__(
        self,
        *,
        ai_engine: AIEngine,
        prompt: str,
        user_msg: str,
    ) -> None:
        super().__init__()
        self._engine = ai_engine
        self._prompt = prompt
        self._user_msg = user_msg
        self.signals = _WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            # The engine exposes `provider` for advanced flows like
            # this. We re-use the same engine so the user can swap the
            # provider (mock vs Ollama) without touching the worker.
            # SYSTEM_PROMPT forces Portuguese responses and reminds the
            # model that file content embedded in the prompt is real.
            response = self._engine.provider.generate(
                self._prompt, system=SYSTEM_PROMPT, temperature=0.3
            )
        except AIServiceUnavailableError as exc:
            self.signals.failed.emit(f"AI service unavailable: {exc.message}")
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.signals.finished.emit(response)
