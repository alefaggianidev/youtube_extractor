import httpx
from typer.testing import CliRunner

import ytkb.cli as cli
from tests.helpers import FIXTURES

runner = CliRunner()
CH = "UCabcdefghijklmnopqrstuv"
FEED = (FIXTURES / "feed_channel.xml").read_bytes()


def _offline(monkeypatch):
    monkeypatch.setattr(cli, "_http_client",
                        lambda: httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=FEED))))


def _init(home):
    assert runner.invoke(cli.app, ["--home", str(home), "init"]).exit_code == 0


def test_channels_add_by_id_takes_name_from_feed(home, monkeypatch):
    _init(home)
    _offline(monkeypatch)
    r = runner.invoke(cli.app, ["--home", str(home), "channels", "add", CH])
    assert r.exit_code == 0, r.output
    assert "Aggiunti 1 canali" in r.output
    r = runner.invoke(cli.app, ["--home", str(home), "channels", "list"])
    assert "Trading Facile" in r.output and CH in r.output


def test_channels_import_disable_remove(home, monkeypatch):
    _init(home)
    r = runner.invoke(cli.app, ["--home", str(home), "channels", "import-takeout",
                                str(FIXTURES / "takeout_subscriptions_it.csv")])
    assert r.exit_code == 0 and "aggiunti 3" in r.output, r.output
    r = runner.invoke(cli.app, ["--home", str(home), "channels", "disable", "Canale Tre"])
    assert r.exit_code == 0, r.output
    text = (home / "config" / "channels.yaml").read_text(encoding="utf-8")
    assert "enabled: false" in text
    r = runner.invoke(cli.app, ["--home", str(home), "channels", "remove", CH])
    assert r.exit_code == 0
    assert CH not in (home / "config" / "channels.yaml").read_text(encoding="utf-8")
    r = runner.invoke(cli.app, ["--home", str(home), "channels", "enable", "inesistente"])
    assert r.exit_code == 1


def test_channels_import_disabled(home):
    _init(home)
    r = runner.invoke(cli.app, ["--home", str(home), "channels", "import-takeout", "--disabled",
                                str(FIXTURES / "takeout_subscriptions_it.csv")])
    assert r.exit_code == 0 and "disattivati" in r.output, r.output
    from ytkb.youtube.channels import load_channels

    assert not any(c.enabled for c in load_channels(home / "config" / "channels.yaml"))


def test_poll_command(home, monkeypatch):
    _init(home)
    _offline(monkeypatch)
    assert runner.invoke(cli.app, ["--home", str(home), "channels", "add", CH]).exit_code == 0
    from ytkb.monitor import Monitor

    monkeypatch.setattr(cli, "_build_monitor", lambda st: Monitor(st.settings, st.db, client=cli._http_client(),
                                                                  pause_s=0))
    r = runner.invoke(cli.app, ["--home", str(home), "poll"])
    assert r.exit_code == 0, r.output
    assert "Nuovi video in coda:" in r.output
