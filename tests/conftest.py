"""Fixture comuni. Nessun test usa la rete: YouTube, Gemini e Telegram sono simulati."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ytkb.config import load_settings
from ytkb.db import open_db

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _no_real_secrets(monkeypatch):
    """Evita che chiavi reali presenti nell'ambiente finiscano nei test."""
    for var in ("GEMINI_API_KEY", "YOUTUBE_API_KEY", "TELEGRAM_BOT_TOKEN", "YTKB_PROXY", "YTKB_HOME"):
        monkeypatch.delenv(var, raising=False)
    os.environ.setdefault("TZ", "UTC")


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """Una cartella di progetto vuota, con i file di esempio della repo."""
    (tmp_path / "config").mkdir()
    for name in ("settings.example.yaml", "channels.example.yaml"):
        src = REPO_ROOT / "config" / name
        (tmp_path / "config" / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / ".env.example").write_text((REPO_ROOT / ".env.example").read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


@pytest.fixture
def settings(home: Path):
    s = load_settings(home, overrides={"llm": {"provider": "fake"}})
    s.ensure_dirs()
    return s


@pytest.fixture
def db(settings):
    database = open_db(settings.db_path)
    yield database
    database.close()


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 10, 27, 10, 0, 0, tzinfo=UTC)


@pytest.fixture
def fine_settings(home: Path):
    """Impostazioni con segmenti piccoli (la trascrizione di prova dura solo 2 minuti)."""
    s = load_settings(home, overrides={
        "llm": {"provider": "fake"},
        "transcript": {"segment_target_s": 8, "segment_max_s": 14},
    })
    s.ensure_dirs()
    return s


@pytest.fixture
def fine_db(fine_settings):
    database = open_db(fine_settings.db_path)
    yield database
    database.close()
