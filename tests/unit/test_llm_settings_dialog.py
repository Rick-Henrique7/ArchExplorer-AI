"""Tests for LlmSettingsDialog + load/save_llm_config (Change 007 — Bloco G)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ui.llm_settings_dialog import (
    LlmSettingsDialog,
    default_llm_config_path,
    load_llm_config,
    save_llm_config,
)


def test_default_config_has_ollama_local_active() -> None:
    cfg = load_llm_config(Path("/nonexistent/config.json"))
    assert cfg["active_provider"] == "ollama_local"
    assert "qwen2.5-coder:3b" in cfg["providers"]["ollama_local"]["model"]


def test_load_returns_default_for_missing_file(tmp_path: Path) -> None:
    cfg = load_llm_config(tmp_path / "missing.json")
    assert "providers" in cfg


def test_load_returns_default_for_invalid_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("not json{", encoding="utf-8")
    cfg = load_llm_config(bad)
    assert cfg["active_provider"] == "ollama_local"


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    cfg = {
        "active_provider": "openai",
        "providers": {
            "openai": {
                "model": "gpt-4o",
                "api_key_env": "OPENAI_API_KEY",
                "temperature": 0.3,
                "max_tokens": 8192,
            },
        },
    }
    out = tmp_path / "config.json"
    save_llm_config(out, cfg)
    loaded = load_llm_config(out)
    assert loaded == cfg


def test_dialog_populates_fields_from_config(qapp) -> None:
    cfg = {
        "active_provider": "anthropic",
        "providers": {
            "anthropic": {
                "model": "claude-3-5-sonnet-20241022",
                "api_key_env": "ANTHROPIC_API_KEY",
                "temperature": 0.7,
                "max_tokens": 8192,
            },
        },
    }
    dlg = LlmSettingsDialog(cfg)
    assert dlg._provider_combo.currentText() == "anthropic"
    assert dlg._model_input.text() == "claude-3-5-sonnet-20241022"
    assert dlg._api_key_env_input.text() == "ANTHROPIC_API_KEY"
    assert abs(dlg._temperature_input.value() - 0.7) < 0.001
    assert dlg._max_tokens_input.value() == 8192


def test_dialog_accept_updates_config(qapp) -> None:
    cfg = {"active_provider": "ollama_local", "providers": {"ollama_local": {}}}
    dlg = LlmSettingsDialog(cfg)
    dlg._model_input.setText("custom-model")
    dlg._temperature_input.setValue(0.55)
    dlg._on_accept()
    out = dlg.updated_config
    assert out["active_provider"] == "ollama_local"
    assert out["providers"]["ollama_local"]["model"] == "custom-model"
    assert abs(out["providers"]["ollama_local"]["temperature"] - 0.55) < 0.001


def test_dialog_omits_empty_optional_fields(qapp) -> None:
    """base_url / api_key_env are only persisted when filled in."""
    cfg = {"active_provider": "openai", "providers": {"openai": {}}}
    dlg = LlmSettingsDialog(cfg)
    dlg._model_input.setText("gpt-4o")
    # Don't touch base_url / api_key_env → should stay absent.
    dlg._on_accept()
    out = dlg.updated_config["providers"]["openai"]
    assert "base_url" not in out
    assert "api_key_env" not in out


def test_dialog_provider_combo_has_all_options(qapp) -> None:
    cfg = {"active_provider": "openai", "providers": {"openai": {}}}
    dlg = LlmSettingsDialog(cfg)
    providers = [
        dlg._provider_combo.itemText(i)
        for i in range(dlg._provider_combo.count())
    ]
    assert {"openai", "anthropic", "gemini", "ollama_local", "cohere"} <= set(providers)


def test_default_config_path_returns_a_path() -> None:
    p = default_llm_config_path()
    assert isinstance(p, Path)
    assert p.suffix == ".json"
