from typer.testing import CliRunner

from ytkb.cli import app

runner = CliRunner()


def test_init_creates_files(home):
    result = runner.invoke(app, ["--home", str(home), "init"])
    assert result.exit_code == 0, result.output
    assert (home / "config" / "settings.yaml").exists()
    assert (home / "config" / "channels.yaml").exists()
    assert (home / ".env").exists()
    assert (home / "data" / "state" / "ytkb.db").exists()


def test_add_status_retry(home):
    assert runner.invoke(app, ["--home", str(home), "init"]).exit_code == 0
    r = runner.invoke(app, ["--home", str(home), "add", "https://youtu.be/dQw4w9WgXcQ", "questo-non-e-un-link"])
    assert r.exit_code == 0, r.output
    assert "In coda: dQw4w9WgXcQ" in r.output
    assert "Link non riconosciuto" in r.output
    r = runner.invoke(app, ["--home", str(home), "add", "dQw4w9WgXcQ"])
    assert "Già presente" in r.output
    r = runner.invoke(app, ["--home", str(home), "status"])
    assert r.exit_code == 0 and "dQw4w9WgXcQ" in r.output
    r = runner.invoke(app, ["--home", str(home), "retry", "dQw4w9WgXcQ"])
    assert r.exit_code == 0 and "Rimesso in coda" in r.output


def test_doctor_offline_runs(home):
    runner.invoke(app, ["--home", str(home), "init"])
    r = runner.invoke(app, ["--home", str(home), "doctor", "--offline"])
    # senza GEMINI_API_KEY il doctor deve segnalarlo (exit 1) ma senza eccezioni
    assert r.exception is None or isinstance(r.exception, SystemExit), r.output
    assert "GEMINI_API_KEY" in r.output


def test_init_uses_examples_from_installed_project(tmp_path):
    """Come nel container: la cartella dati è vuota, gli esempi stanno nel progetto installato."""
    empty_home = tmp_path / "dati"
    empty_home.mkdir()
    result = runner.invoke(app, ["--home", str(empty_home), "init"])
    assert result.exit_code == 0, result.output
    assert (empty_home / "config" / "settings.yaml").exists()
    assert (empty_home / ".env").exists()
