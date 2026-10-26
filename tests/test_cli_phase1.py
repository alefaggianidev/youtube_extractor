from datetime import UTC, datetime

from typer.testing import CliRunner

import ytkb.cli as cli
from tests.helpers import make_ctx
from ytkb.config import load_settings
from ytkb.db import open_db
from ytkb.pipeline.runner import Pipeline

runner = CliRunner()


def _patch_pipeline(monkeypatch, home):
    def build(st):
        s = load_settings(home, overrides={"llm": {"provider": "fake"},
                                            "transcript": {"segment_target_s": 8, "segment_max_s": 14}})
        return Pipeline(make_ctx(s, st.db, clock=lambda: datetime(2026, 10, 27, 10, tzinfo=UTC)))

    monkeypatch.setattr(cli, "_build_pipeline", build)


def test_add_now_render_costs(home, monkeypatch):
    assert runner.invoke(cli.app, ["--home", str(home), "init"]).exit_code == 0
    _patch_pipeline(monkeypatch, home)
    r = runner.invoke(cli.app, ["--home", str(home), "add", "--now", "https://youtu.be/dQw4w9WgXcQ"])
    assert r.exit_code == 0, r.output
    assert "report.md" in r.output and "✅" in r.output

    r = runner.invoke(cli.app, ["--home", str(home), "render", "dQw4w9WgXcQ"])
    assert r.exit_code == 0, r.output
    assert "Rigenerati" in r.output

    r = runner.invoke(cli.app, ["--home", str(home), "costs"])
    assert r.exit_code == 0 and "analysis" in r.output

    r = runner.invoke(cli.app, ["--home", str(home), "show", "dQw4w9WgXcQ"])
    assert r.exit_code == 0 and "Report pronto" in r.output


def test_process_runs_pending(home, monkeypatch):
    assert runner.invoke(cli.app, ["--home", str(home), "init"]).exit_code == 0
    db = open_db(load_settings(home).db_path)
    db.add_video("dQw4w9WgXcQ", source="manual", priority=10)
    _patch_pipeline(monkeypatch, home)
    r = runner.invoke(cli.app, ["--home", str(home), "process"])
    assert r.exit_code == 0 and "Video lavorati: 1" in r.output, r.output


def test_missing_gemini_key_gives_clear_error(home):
    assert runner.invoke(cli.app, ["--home", str(home), "init"]).exit_code == 0
    r = runner.invoke(cli.app, ["--home", str(home), "add", "--now", "dQw4w9WgXcQ"])
    assert "GEMINI_API_KEY mancante" in str(r.exception)
