"""Background workers for the LPS module (Change 007 — Bloco E).

Two ``QRunnable`` workers live here:

- :class:`LpsSolverWorker` — runs :class:`VariabilitySolver` (pysat) on
  the current feature model + selection. Pure CPU work; runs off the
  UI thread so the canvas stays responsive.
- :class:`LpsGeneratorWorker` — runs :class:`TemplateEngine` for every
  selected component, writes the resulting tree to disk, and records
  the run via :class:`LpsService.record_run`. I/O bound; off-thread
  so the UI doesn't freeze while templates render.

Both follow the same pattern as the existing AI workers
(``app.ui.analysis_worker``): a companion :class:`_LpsWorkerSignals`
carries Qt signals because ``QRunnable`` is not a ``QObject``.

The LLM worker (:class:`LpsLlmWorker`) lives in Bloco F; this module
stays focused on the solver + generator paths.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from app.services import (
    LpsService,
    TemplateEngine,
    VariabilitySolver,
)
from app.services.lps_models import FeatureModel, LpsComponent

_logger = logging.getLogger(__name__)


class _LpsWorkerSignals(QObject):
    """Companion signals for the solver + generator workers."""

    finished = Signal(object)   # result payload (typed per worker)
    failed = Signal(str)        # error message


class _LpsGeneratorSignals(QObject):
    """Companion signals for the generator (has progress in addition)."""

    finished = Signal(object)   # GeneratorResult
    failed = Signal(str)
    progress = Signal(int, int, str)   # done, total, current_file


class LpsSolverWorker(QRunnable):
    """Run the SAT solver on ``feature_model`` + ``selection``.

    Emits ``finished(ValidationResult)`` on success or ``failed(msg)``
    on any unexpected exception. The pysat call itself can raise
    ``LpsValidationError`` for malformed models — that path is
    surfaced through ``failed`` so the UI can show it without
    crashing the event loop.
    """

    def __init__(
        self,
        *,
        feature_model: FeatureModel,
        selection: list[str],
        solver: VariabilitySolver | None = None,
    ) -> None:
        super().__init__()
        self._model = feature_model
        self._selection = list(selection)
        self._solver = solver or VariabilitySolver()
        self.signals = _LpsWorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            encoded = self._solver.encode(self._model)
            result = self._solver.is_satisfiable(encoded, self._selection)
        except Exception as exc:  # noqa: BLE001 — Qt slot boundary
            _logger.exception("LpsSolverWorker failed")
            self.signals.failed.emit(str(exc))
            return
        self.signals.finished.emit(result)


@dataclass(frozen=True)
class GeneratorResult:
    """Result payload of :class:`LpsGeneratorWorker`.

    The MainWindow records a :class:`ProductRun` itself (the worker
    doesn't know about the service) and shows a notification based
    on this dataclass.
    """

    output_dir: str
    file_count: int
    duration_ms: int
    resolved_node_ids: tuple[str, ...]
    failed_files: tuple[str, ...] = ()


class LpsGeneratorWorker(QRunnable):
    """Render Jinja2 templates for each selected component.

    The worker resolves the feature model once via
    :class:`VariabilitySolver` (so we know which nodes are selected),
    then looks up the matching :class:`LpsComponent` for each node
    that has a ``component_id``, and renders its ``jinja_template``
    into the output directory.

    Progress is reported through ``signals.progress(done, total,
    file_name)`` so the UI can update a status bar without blocking
    on completion.
    """

    def __init__(
        self,
        *,
        feature_model: FeatureModel,
        selection: list[str],
        components_by_id: dict[str, LpsComponent],
        template_engine: TemplateEngine,
        output_dir: Path,
        service: LpsService | None = None,
        solver: VariabilitySolver | None = None,
    ) -> None:
        super().__init__()
        self._model = feature_model
        self._selection = list(selection)
        self._components_by_id = dict(components_by_id)
        self._template_engine = template_engine
        self._output_dir = Path(output_dir)
        # ``service`` and ``solver`` are optional for tests; in the
        # real wiring the MainWindow always passes them.
        self._service = service
        self._solver = solver or VariabilitySolver()
        # QRunnable is not a QObject, so progress (which needs
        # Signal-on-QObject) lives on a separate companion.
        self.signals = _LpsGeneratorSignals()

    @Slot()
    def run(self) -> None:
        start = time.perf_counter()
        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)
            encoded = self._solver.encode(self._model)
            validation = self._solver.is_satisfiable(encoded, self._selection)
            if not validation.is_valid:
                self.signals.failed.emit(
                    "Seleção inválida — rode Validar antes de gerar."
                )
                return
            selected_ids = set(validation.model)

            # Collect (component, template) pairs to render.
            work: list[tuple[LpsComponent, str]] = []
            for node in self._model.nodes:
                if node.id not in selected_ids:
                    continue
                if not node.component_id:
                    continue
                comp = self._components_by_id.get(node.component_id)
                if comp is None:
                    _logger.warning(
                        "selected node references missing component",
                        node_id=node.id, component_id=node.component_id,
                    )
                    continue
                if not comp.jinja_template:
                    _logger.info(
                        "skipping component without template",
                        component=comp.id,
                    )
                    continue
                work.append((comp, comp.jinja_template))

            total = len(work)
            file_count = 0
            failed: list[str] = []
            for index, (comp, template_name) in enumerate(work, start=1):
                # Path: <output>/<slug(component.name)>/
                # Strip the trailing ``.j2``; keep whatever extension
                # preceded it (.md, .py, .yml, ...) or fall back to .txt.
                if template_name.endswith(".j2"):
                    base = template_name[:-3]
                else:
                    base = template_name
                last_dot = base.rfind(".")
                suffix = base[last_dot:] if last_dot >= 0 else ".txt"
                file_stem = base[:last_dot] if last_dot >= 0 else base
                out_path = (
                    self._output_dir
                    / _slugify(comp.name)
                    / f"{Path(file_stem).name}{suffix}"
                )
                self.signals.progress.emit(index - 1, total, str(out_path))
                try:
                    context = {
                        "component": comp.to_dict(),
                        "model": self._model.to_dict(),
                    }
                    self._template_engine.render(
                        template_name, context, out_path,
                    )
                    file_count += 1
                except Exception as exc:  # per-template failure
                    _logger.exception(
                        "failed to render template", template=template_name,
                    )
                    failed.append(f"{template_name}: {exc}")
            self.signals.progress.emit(total, total, "")

            duration_ms = int((time.perf_counter() - start) * 1000)
            result = GeneratorResult(
                output_dir=str(self._output_dir),
                file_count=file_count,
                duration_ms=duration_ms,
                resolved_node_ids=tuple(sorted(selected_ids)),
                failed_files=tuple(failed),
            )
            # Record the run if the service is wired.
            if self._service is not None:
                try:
                    self._service.record_run(
                        feature_model_id=self._model.id,
                        resolved_json=json.dumps({
                            "selected": result.resolved_node_ids,
                            "duration_ms": result.duration_ms,
                            "file_count": result.file_count,
                        }),
                        output_dir=result.output_dir,
                        file_count=result.file_count,
                        duration_ms=result.duration_ms,
                        status=(
                            "FAILED" if failed and file_count == 0
                            else "PARTIAL" if failed
                            else "SUCCESS"
                        ),
                        error_message=(
                            "; ".join(failed) if failed else None
                        ),
                    )
                except Exception as exc:  # never break the worker on audit failure
                    _logger.warning(
                        "could not record product run", error=str(exc),
                    )
        except Exception as exc:  # noqa: BLE001 — Qt slot boundary
            _logger.exception("LpsGeneratorWorker failed")
            self.signals.failed.emit(str(exc))
            return
        self.signals.finished.emit(result)


# ----- Helpers -----------------------------------------------------------

# Suffix to write the rendered file with. Keeps the template author's
# intent: a .yml.j2 template becomes .yml; .py.j2 → .py; .md.j2 → .md.
_SUFFIX_FOR_TEMPLATE: dict[str, str] = {
    ".yml.j2": ".yml",
    ".yaml.j2": ".yaml",
    ".py.j2": ".py",
    ".md.j2": ".md",
    ".html.j2": ".html",
    ".json.j2": ".json",
}


def _slugify(value: str) -> str:
    """Filesystem-safe ASCII slug from ``value``."""
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "component"

