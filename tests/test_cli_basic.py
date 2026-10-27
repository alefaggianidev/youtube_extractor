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


def test_deep_checks_report_failures_without_crashing(settings, monkeypatch):
    """Senza rete i controlli profondi falliscono, ma con un messaggio e senza eccezioni."""
    import ytkb.doctor as doctor

    monkeypatch.setattr("ytkb.youtube.metadata.fetch_metadata",
                        lambda vid, s: (_ for _ in ()).throw(RuntimeError("Sign in to confirm you're not a bot")))

    class FakeCapturer:
        def __init__(self, s):
            pass

        def capture_frames(self, *a, **k):
            raise RuntimeError("bloccato")

    monkeypatch.setattr("ytkb.youtube.media.FrameCapturer", FakeCapturer)

    class FakeApi:
        def list(self, vid):
            import youtube_transcript_api as yta
            raise yta.TranscriptsDisabled(vid)

    monkeypatch.setattr("youtube_transcript_api.YouTubeTranscriptApi", FakeApi)
    checks = {c.name: c for c in doctor.deep_checks(settings)}  # provider "fake": Gemini simulato
    assert not checks["YouTube → metadati (yt-dlp)"].ok and "not a bot" in checks["YouTube → metadati (yt-dlp)"].detail
    assert checks["YouTube → sottotitoli (youtube-transcript-api)"].ok
    assert not checks["YouTube → download di 3 secondi (screenshot)"].ok
    assert checks["Gemini → chiamata di prova"].ok and "finto" in checks["Gemini → chiamata di prova"].detail


def test_cli_does_not_interpret_brackets_in_titles(home):
    """Titoli ed errori con parentesi quadre (es. "[LIVE]", "[/x]") vanno stampati così come sono."""
    from ytkb.config import load_settings
    from ytkb.db import open_db

    runner.invoke(app, ["--home", str(home), "init"])
    db = open_db(load_settings(home).db_path)
    db.add_video("dQw4w9WgXcQ", source="manual", title="[LIVE] Apertura [/bold] mercati")
    db.update_video("dQw4w9WgXcQ", last_error="[youtube] dQw4w9WgXcQ: errore")
    r = runner.invoke(app, ["--home", str(home), "status"])
    assert r.exit_code == 0, r.output
    assert "[LIVE] Apertura [/bold] mercati" in r.output and "[youtube] dQw4w9WgXcQ" in r.output
    r = runner.invoke(app, ["--home", str(home), "show", "dQw4w9WgXcQ"])
    assert r.exit_code == 0 and "[LIVE]" in r.output


def test_ytdlp_messages_are_cleaned():
    from ytkb.youtube.ytdlp import clean_message

    raw = ("ERROR: [youtube] abc: Unable to download API page: ('Unable to connect to proxy') (caused by "
           "ProxyError('x')); please report this issue on  https://github.com/yt-dlp/yt-dlp/issues?q= , filling out "
           "the appropriate issue template. Confirm you are on the latest version using  yt-dlp -U")
    assert clean_message(raw) == "[youtube] abc: Unable to download API page: ('Unable to connect to proxy')"
