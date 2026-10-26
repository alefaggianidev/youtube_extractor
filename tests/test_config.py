import pytest
from pydantic import ValidationError

from ytkb.config import FilterSettings, load_settings
from ytkb.errors import ConfigError


def test_defaults_without_settings_file(tmp_path):
    s = load_settings(tmp_path)
    assert s.source_file is None
    assert s.llm.models.analysis.startswith("gemini-")
    assert s.archive_dir == (tmp_path / "data" / "archive").resolve()
    assert s.db_path == (tmp_path / "data" / "state" / "ytkb.db").resolve()


def test_example_file_is_valid_and_complete(home):
    """Il file di esempio deve caricarsi senza errori e coincidere con i default del codice."""
    (home / "config" / "settings.yaml").write_text(
        (home / "config" / "settings.example.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    from_file = load_settings(home)
    defaults = load_settings(home / "nonexistent")
    assert from_file.source_file is not None
    assert from_file.model_dump() == defaults.model_dump()


def test_unknown_key_is_reported(home):
    (home / "config" / "settings.yaml").write_text("llm:\n  modell: x\n", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_settings(home)
    assert "llm.modell" in str(exc.value)


def test_secrets_from_env_file(home, monkeypatch):
    (home / ".env").write_text("GEMINI_API_KEY=abc123segreta\nTELEGRAM_BOT_TOKEN=\n", encoding="utf-8")
    s = load_settings(home)
    assert s.secrets.reveal(s.secrets.gemini_api_key) == "abc123segreta"
    assert "abc123segreta" in s.secrets.values_to_redact()
    assert "abc123segreta" not in repr(s.secrets)


def test_env_var_wins_over_env_file(home, monkeypatch):
    (home / ".env").write_text("GEMINI_API_KEY=dal_file\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_API_KEY", "dalla_variabile")
    s = load_settings(home)
    assert s.secrets.reveal(s.secrets.gemini_api_key) == "dalla_variabile"


def test_filter_overrides_per_channel():
    base = FilterSettings()
    merged = base.merged({"max_duration_s": 600})
    assert merged.max_duration_s == 600
    assert merged.skip_shorts == base.skip_shorts
    with pytest.raises(ValidationError):
        base.merged({"parola_sbagliata": 1})
