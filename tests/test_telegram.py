"""Telegram: client, notifiche e bot, con la Bot API simulata (nessuna rete)."""

import json
import threading
from pathlib import Path

import httpx
import pytest

from tests.helpers import make_ctx
from ytkb.errors import ConfigError, TemporaryError
from ytkb.llm.fake import FakeProvider
from ytkb.models import VideoStatus
from ytkb.notify.format import summary_html
from ytkb.notify.telegram import TelegramBot, TelegramClient, TelegramNotifier

TOKEN = "123456:SEGRETISSIMO-token"
ME = 111
STRANGER = 999


class FakeApi:
    """Bot API finta: registra le chiamate e risponde secondo ``script``."""

    def __init__(self, script=None, updates=None):
        self.calls = []
        self.script = script or {}
        self.updates = updates or []

    def handler(self, request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        assert TOKEN in request.url.path
        if request.headers.get("content-type", "").startswith("application/json"):
            payload = json.loads(request.content)
        else:
            payload = {"_multipart": True, "_body": request.content}
        self.calls.append((method, payload))
        if method in self.script and self.script[method]:
            status, body = self.script[method].pop(0)
            return httpx.Response(status, json=body)
        if method == "getUpdates":
            ups, self.updates = self.updates, []
            return httpx.Response(200, json={"ok": True, "result": ups})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": len(self.calls)}})

    def client(self):
        return TelegramClient(TOKEN, httpx.Client(transport=httpx.MockTransport(self.handler)))

    def sent(self, method="sendMessage"):
        return [p for m, p in self.calls if m == method]


def _msg(chat, text, update_id=1):
    return {"update_id": update_id, "message": {"chat": {"id": chat}, "text": text}}


# --- client -------------------------------------------------------------------------------------
def test_client_errors(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    api = FakeApi(script={"sendMessage": [(429, {"ok": False, "parameters": {"retry_after": 1}})]})
    api.client().send_message(ME, "ciao")
    assert len(api.sent()) == 2  # ritentato dopo il 429

    api = FakeApi(script={"sendMessage": [(401, {"ok": False, "description": "Unauthorized"})]})
    with pytest.raises(ConfigError, match="Token Telegram"):
        api.client().send_message(ME, "ciao")

    api = FakeApi(script={"sendMessage": [(400, {"ok": False, "description": "Bad Request: can't parse entities"})]})
    api.client().send_message(ME, "<b>rotto")
    assert api.sent()[1]["text"] == "rotto" and "parse_mode" not in api.sent()[1]

    def down(request):
        raise httpx.ConnectError(f"impossibile connettersi a {request.url}")

    with pytest.raises(TemporaryError) as exc:
        TelegramClient(TOKEN, httpx.Client(transport=httpx.MockTransport(down))).send_message(ME, "x")
    assert TOKEN not in str(exc.value) and exc.value.__cause__ is None  # il token non trapela


# --- notifiche ----------------------------------------------------------------------------------
def test_notifier_sends_summary_and_report(tmp_path):
    report = tmp_path / "report.html"
    report.write_text("<html>ok</html>", encoding="utf-8")
    api = FakeApi()
    n = TelegramNotifier(api.client(), [ME, 222])
    n.video_done(video_id="v", title="Titolo <x>", channel="C", summary_html="<b>riassunto</b>", report_html=report,
                 requested_by=str(ME))
    assert [p["chat_id"] for p in api.sent()] == [ME]  # solo a chi l'ha chiesto
    docs = api.sent("sendDocument")
    assert len(docs) == 1 and b"report.html" in docs[0]["_body"] and b"Titolo &lt;x&gt;" in docs[0]["_body"]
    api2 = FakeApi()
    TelegramNotifier(api2.client(), [ME, 222]).video_failed(video_id="v", title="T", error="boom",
                                                             requested_by=None)
    assert [p["chat_id"] for p in api2.sent()] == [ME, 222]  # video automatico: a tutte le chat autorizzate
    assert "ytkb retry v" in api2.sent()[0]["text"]


def test_summary_html_escapes_and_limits(settings):
    from tests.test_report import _vm

    vm, _ = _vm(settings, title="A <b>& B")
    text = summary_html(vm)
    assert "A &lt;b&gt;&amp; B" in text and "⚡ <b>In 30 secondi</b>" in text
    assert "🟢 <b>BTCUSD</b> Rialzista (1D): supporto 60.000 🗣️" in text
    vm.tldr = ["x" * 500] * 20
    assert len(summary_html(vm)) <= 4000


# --- bot ------------------------------------------------------------------------------------------
def test_bot_rejects_strangers_and_enqueues_links(db):
    api = FakeApi()
    bot = TelegramBot(api.client(), db, [ME])
    bot.handle_update(_msg(STRANGER, "https://youtu.be/dQw4w9WgXcQ"))
    assert "non autorizzata" in api.sent()[-1]["text"] and str(STRANGER) in api.sent()[-1]["text"]
    assert db.get_video("dQw4w9WgXcQ") is None

    bot.handle_update(_msg(ME, "guarda https://youtu.be/dQw4w9WgXcQ e https://www.youtube.com/watch?v=abcdefghijk"))
    row = db.get_video("dQw4w9WgXcQ")
    assert row.source == "telegram" and row.requested_by == str(ME) and row.priority == 10
    assert "In coda" in api.sent()[-1]["text"] and db.get_video("abcdefghijk") is not None

    bot.handle_update(_msg(ME, "/stato"))
    assert "Stato" in api.sent()[-1]["text"]
    bot.handle_update(_msg(ME, "ciao"))
    assert "link YouTube" in api.sent()[-1]["text"]


def test_bot_handles_known_videos(db):
    api = FakeApi()
    resent = []
    bot = TelegramBot(api.client(), db, [ME], resend_report=lambda chat, vid: resent.append(vid) or True)
    db.add_video("dQw4w9WgXcQ", source="rss", title="Fatto")
    db.update_video("dQw4w9WgXcQ", status=VideoStatus.DONE)
    bot.handle_update(_msg(ME, "https://youtu.be/dQw4w9WgXcQ"))
    assert resent == ["dQw4w9WgXcQ"] and "Già analizzato" in api.sent()[-1]["text"]
    db.update_video("dQw4w9WgXcQ", status=VideoStatus.FAILED)
    bot.handle_update(_msg(ME, "https://youtu.be/dQw4w9WgXcQ"))
    assert db.get_video("dQw4w9WgXcQ").status == VideoStatus.QUEUED


def test_bot_poll_once_saves_offset_and_run_stops(db):
    api = FakeApi(updates=[_msg(ME, "/start", 41), _msg(ME, "/stato", 42)])
    bot = TelegramBot(api.client(), db, [ME])
    assert bot.poll_once(timeout=0) == 2
    assert db.kv_get("telegram_offset") == "43"
    stop = threading.Event()
    t = threading.Thread(target=bot.run, args=(stop,))
    t.start()
    stop.set()
    t.join(timeout=5)
    assert not t.is_alive()


# --- integrazione con la pipeline --------------------------------------------------------------
class RecordingNotifier:
    def __init__(self, fail=False):
        self.done, self.failed, self.fail = [], [], fail

    def video_done(self, **kw):
        if self.fail:
            raise TemporaryError("Telegram giù")
        self.done.append(kw)

    def video_failed(self, **kw):
        self.failed.append(kw)


def test_pipeline_notifies(fine_settings, fine_db, fixed_now):
    from tests.test_pipeline import _analysis_responder
    from ytkb.pipeline.runner import Pipeline

    notifier = RecordingNotifier()
    ctx = make_ctx(fine_settings, fine_db, llm=FakeProvider(responses={"analysis": _analysis_responder}),
                   notifier=notifier, clock=lambda: fixed_now)
    row = Pipeline(ctx).process_now("dQw4w9WgXcQ")
    assert row.status == VideoStatus.DONE
    sent = notifier.done[0]
    assert "BTC rialzista" in sent["summary_html"] and Path(sent["report_html"]).name == "report.html"


def test_notification_failure_does_not_fail_video(fine_settings, fine_db, fixed_now):
    from tests.test_pipeline import _analysis_responder
    from ytkb.pipeline.runner import Pipeline

    ctx = make_ctx(fine_settings, fine_db, llm=FakeProvider(responses={"analysis": _analysis_responder}),
                   notifier=RecordingNotifier(fail=True), clock=lambda: fixed_now)
    assert Pipeline(ctx).process_now("dQw4w9WgXcQ").status == VideoStatus.DONE
    assert any("Notifica non inviata" in e["message"] for e in fine_db.events_of("dQw4w9WgXcQ"))


def test_cli_telegram_commands(home, monkeypatch):
    from typer.testing import CliRunner

    import ytkb.cli as cli

    runner = CliRunner()
    assert runner.invoke(cli.app, ["--home", str(home), "init"]).exit_code == 0
    api = FakeApi(updates=[{"update_id": 1, "message": {"chat": {"id": ME, "first_name": "Ale"}, "text": "/start"}}])
    monkeypatch.setattr(cli, "_telegram_client", lambda st: api.client())
    r = runner.invoke(cli.app, ["--home", str(home), "telegram", "chat-id"])
    assert r.exit_code == 0 and str(ME) in r.output and "Ale" in r.output
    r = runner.invoke(cli.app, ["--home", str(home), "telegram", "test"])
    assert r.exit_code == 1  # nessuna chat autorizzata
    settings_file = home / "config" / "settings.yaml"
    settings_file.write_text(settings_file.read_text(encoding="utf-8").replace(
        "allowed_chat_ids: []", f"allowed_chat_ids: [{ME}]"), encoding="utf-8")
    r = runner.invoke(cli.app, ["--home", str(home), "telegram", "test"])
    assert r.exit_code == 0, r.output
    assert api.sent()[-1]["chat_id"] == ME
