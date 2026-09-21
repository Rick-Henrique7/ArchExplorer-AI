"""Settings dialog for the LLM adapter (Change 007 — Bloco G).

Allows the user to pick the active provider, set the model name,
and toggle the API key environment variable. Persists to
``config/llm_config.json`` next to the repo and (separately) the
catalog DB path to QSettings under ``catalog/db_path`` / ``llm/...``.

Why both? The JSON config is easy to commit / share with teammates;
the QSettings is convenient for per-user overrides. The JSON wins
when both are present.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.services.llm_adapter import _PROVIDER_DEFAULTS


class LlmSettingsDialog(QDialog):
    """Provider + model + temperature + max_tokens."""

    def __init__(
        self,
        config: dict[str, Any],
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("Configurações do LLM")
        self.setMinimumWidth(420)
        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Escolha o provedor de IA. As chaves de API são lidas de "
            "variáveis de ambiente — nada é gravado em disco.",
            self,
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()

        self._provider_combo = QComboBox(self)
        for provider in _PROVIDER_DEFAULTS:
            self._provider_combo.addItem(provider)
        form.addRow("Provedor:", self._provider_combo)

        self._model_input = QLineEdit(self)
        self._model_input.setPlaceholderText("ex: qwen2.5-coder:3b, gpt-4o")
        form.addRow("Modelo:", self._model_input)

        self._base_url_input = QLineEdit(self)
        self._base_url_input.setPlaceholderText(
            "http://localhost:11434  (apenas ollama_local)",
        )
        form.addRow("Base URL:", self._base_url_input)

        self._api_key_env_input = QLineEdit(self)
        self._api_key_env_input.setPlaceholderText(
            "OPENAI_API_KEY, ANTHROPIC_API_KEY, ...",
        )
        form.addRow("Env var da chave:", self._api_key_env_input)

        # Numeric tunables.
        spin_row = QHBoxLayout()
        self._temperature_input = QDoubleSpinBox(self)
        self._temperature_input.setRange(0.0, 2.0)
        self._temperature_input.setSingleStep(0.1)
        self._temperature_input.setDecimals(2)
        spin_row.addWidget(self._temperature_input)
        spin_row.addWidget(QLabel("max_tokens:", self))
        self._max_tokens_input = QSpinBox(self)
        self._max_tokens_input.setRange(64, 32_000)
        self._max_tokens_input.setSingleStep(256)
        spin_row.addWidget(self._max_tokens_input)
        spin_row.addStretch(1)
        spin_row_container = QWidget(self)
        spin_row_container.setLayout(spin_row)
        form.addRow("Temperatura:", spin_row_container)

        layout.addLayout(form)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self._buttons.accepted.connect(self._on_accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _populate(self) -> None:
        active = self._config.get("active_provider", "")
        if active:
            idx = self._provider_combo.findText(active)
            if idx >= 0:
                self._provider_combo.setCurrentIndex(idx)
        providers = self._config.get("providers") or {}
        if active and active in providers:
            cfg = providers[active]
            self._model_input.setText(cfg.get("model", ""))
            self._base_url_input.setText(cfg.get("base_url", ""))
            self._api_key_env_input.setText(cfg.get("api_key_env", ""))
            self._temperature_input.setValue(float(cfg.get("temperature", 0.2)))
            self._max_tokens_input.setValue(int(cfg.get("max_tokens", 4096)))
        else:
            # Defaults from the first provider.
            first = self._provider_combo.itemText(0)
            self._model_input.setText(_PROVIDER_DEFAULTS[first]["default_model"])
            self._temperature_input.setValue(0.2)
            self._max_tokens_input.setValue(4096)

    def _on_accept(self) -> None:
        provider = self._provider_combo.currentText()
        providers = dict(self._config.get("providers") or {})
        providers[provider] = {
            "model": self._model_input.text().strip(),
            "temperature": self._temperature_input.value(),
            "max_tokens": self._max_tokens_input.value(),
        }
        if self._base_url_input.text().strip():
            providers[provider]["base_url"] = self._base_url_input.text().strip()
        if self._api_key_env_input.text().strip():
            providers[provider]["api_key_env"] = self._api_key_env_input.text().strip()
        self._config["active_provider"] = provider
        self._config["providers"] = providers
        self.accept()

    @property
    def updated_config(self) -> dict[str, Any]:
        return self._config


def load_llm_config(path: Path) -> dict[str, Any]:
    """Read the JSON config, falling back to defaults."""
    if not path.exists():
        return _default_config()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_config()
    # Sanity: ensure required keys exist.
    if "providers" not in data:
        data["providers"] = {}
    if "active_provider" not in data:
        # Default to ollama_local if available, else the first key.
        if "ollama_local" in data["providers"]:
            data["active_provider"] = "ollama_local"
        elif data["providers"]:
            data["active_provider"] = next(iter(data["providers"]))
        else:
            data["active_provider"] = "ollama_local"
            data["providers"]["ollama_local"] = {}
    return data


def save_llm_config(path: Path, config: dict[str, Any]) -> None:
    """Persist the JSON config to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _default_config() -> dict[str, Any]:
    return {
        "active_provider": "ollama_local",
        "providers": {
            "ollama_local": {
                "model": "qwen2.5-coder:3b",
                "base_url": "http://localhost:11434",
                "temperature": 0.2,
                "max_tokens": 4096,
            },
            "openai": {
                "model": "gpt-4o",
                "api_key_env": "OPENAI_API_KEY",
                "temperature": 0.2,
                "max_tokens": 4096,
            },
            "anthropic": {
                "model": "claude-3-5-sonnet-20241022",
                "api_key_env": "ANTHROPIC_API_KEY",
                "temperature": 0.2,
                "max_tokens": 4096,
            },
        },
    }


def default_llm_config_path() -> Path:
    """The default location of ``llm_config.json``.

    Resolved as ``<repo>/config/llm_config.json`` if a ``config``
    directory exists at the project root, else
    ``~/Documents/ArchExplorer/llm_config.json``.
    """
    # Repo-relative path.
    repo_config = Path(__file__).resolve().parent.parent.parent / "config"
    if repo_config.exists():
        return repo_config / "llm_config.json"
    return Path.home() / "Documents" / "ArchExplorer" / "llm_config.json"
