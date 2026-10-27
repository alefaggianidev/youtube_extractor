"""Fase 3: feed RSS, YouTube Data API, canali, monitor e demone (rete simulata con httpx.MockTransport)."""

import json
import threading
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from tests.helpers import FIXTURES
from ytkb.config import load_settings
from ytkb.db import open_db
from ytkb.errors import ConfigError, PermanentError
from ytkb.models import VideoStatus
from ytkb.monitor import Monitor
from ytkb.youtube.channels import (
    ChannelConfig,
    append_channels,
    channel_filter_lookup,
    load_channels,
    parse_takeout_csv,
    resolve_channel_ref,
    rewrite_channels,
    sync_to_db,
)
from ytkb.youtube.dataapi import DataApi, DataApiError
from ytkb.youtube.feeds import FeedUnavailable, fetch_feed, parse_feed

CH = "UCabcdefghijklmnopqrstuv"
NOW = datetime(2026, 10, 27, 10, 0, tzinfo=UTC)
FEED = (FIXTURES / "feed_channel.xml").read_bytes()


def _client(routes):
    """routes: funzione(request) -> httpx.Response"""
    return httpx.Client(transport=httpx.MockTransport(routes))


def _uploads_json():
    return {"items": [{"snippet": {"title": "Dalla Data API", "channelTitle": "Trading Facile"},
                       "contentDetails": {"videoId": "apivideo001", "videoPublishedAt": "2026-10-27T09:00:00Z"}}]}


# --- feed -----------------------------------------------------------------------------------
def test_parse_feed():
    entries = parse_feed(FEED)
    assert [e.video_id for e in entries] == ["newvideo001", "shortvid001", "newvideo002", "oldvideo001"]
    first = entries[0]
    assert first.channel_id == CH and first.channel_title == "Trading Facile"
    assert first.published == datetime(2026, 10, 27, 8, 30, tzinfo=UTC)
    assert entries[1].is_short and not first.is_short


def test_fetch_feed_errors():
    with pytest.raises(FeedUnavailable, match="404"):
        fetch_feed("https://www.youtube.com/feeds/videos.xml?channel_id=x", _client(lambda r: httpx.Response(404)))

    def boom(request):
        raise httpx.ConnectError("no route")

    with pytest.raises(FeedUnavailable):
        fetch_feed("https://www.youtube.com/feeds/videos.xml?channel_id=x", _client(boom))


# --- Data API ---------------------------------------------------------------------------------
def test_dataapi_recent_uploads_and_errors():
    seen = {}

    def routes(request):
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=_uploads_json())

    api = DataApi("KEY", _client(routes))
    items = api.recent_uploads(CH)
    assert seen["params"]["playlistId"] == "UU" + CH[2:] and seen["params"]["key"] == "KEY"
    assert items[0].video_id == "apivideo001" and items[0].published == datetime(2026, 10, 27, 9, tzinfo=UTC)

    quota = {"error": {"errors": [{"reason": "quotaExceeded"}]}}
    with pytest.raises(DataApiError, match="quota"):
        DataApi("KEY", _client(lambda r: httpx.Response(403, json=quota))).recent_uploads(CH)
    bad_key = {"error": {"errors": [{"reason": "keyInvalid"}]}}
    with pytest.raises(PermanentError, match="YOUTUBE_API_KEY"):
        DataApi("KEY", _client(lambda r: httpx.Response(400, json=bad_key))).recent_uploads(CH)


def test_dataapi_channel_by_handle():
    def routes(request):
        assert request.url.params["forHandle"] == "@TradingFacile"
        return httpx.Response(200, json={"items": [{"id": CH, "snippet": {"title": "Trading Facile"}}]})

    assert DataApi("K", _client(routes)).channel_by_handle("@TradingFacile") == (CH, "Trading Facile")


# --- channels.yaml ----------------------------------------------------------------------------
def test_append_keeps_comments_and_validates(home):
    path = home / "config" / "channels.yaml"
    path.write_text((home / "config" / "channels.example.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    assert load_channels(path) == []
    added = append_channels(path, [ChannelConfig(id=CH, name="Trading Facile"),
                                   ChannelConfig(id="UCzyxwvutsrqponmlkjihgfe", name="Macro: Mercati",
                                                 filters={"max_duration_s": 600})])
    assert added == 2
    text = path.read_text(encoding="utf-8")
    assert "ytkb channels import-takeout" in text  # commenti originali conservati
    chans = load_channels(path)
    assert [c.name for c in chans] == ["Trading Facile", "Macro: Mercati"]
    assert chans[1].filters == {"max_duration_s": 600}
    assert append_channels(path, [ChannelConfig(id=CH)]) == 0  # duplicato


def test_append_to_inline_empty_list_and_rewrite(tmp_path):
    path = tmp_path / "channels.yaml"
    path.write_text("channels: []\n", encoding="utf-8")
    append_channels(path, [ChannelConfig(id=CH, name="A")])
    assert [c.id for c in load_channels(path)] == [CH]
    rewrite_channels(path, [ChannelConfig(id=CH, name="A", enabled=False)])
    assert load_channels(path)[0].enabled is False
    rewrite_channels(path, [])
    assert load_channels(path) == []


def test_invalid_channels_file(tmp_path):
    path = tmp_path / "channels.yaml"
    path.write_text("channels:\n  - id: nonvalido\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="non valido"):
        load_channels(path)
    path.write_text(f"channels:\n  - id: {CH}\n    filters: {{durata: 3}}\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_channels(path)


def test_takeout_csv_any_language_with_bom():
    chans = parse_takeout_csv((FIXTURES / "takeout_subscriptions_it.csv").read_text(encoding="utf-8"))
    assert [c.id for c in chans] == [CH, "UCzyxwvutsrqponmlkjihgfe", "UCaaaaaaaaaaaaaaaaaaaaaa"]
    assert chans[1].name == "Macro, Mercati & Co"


def test_sync_to_db_and_filter_lookup(settings, db):
    path = settings.channels_file
    append_channels(path, [ChannelConfig(id=CH, name="A", filters={"skip_shorts": False})])
    sync_to_db(load_channels(path), db)
    assert db.get_channel(CH).enabled
    lookup = channel_filter_lookup(settings)
    assert lookup(CH) == {"skip_shorts": False}
    rewrite_channels(path, [])
    import os
    os.utime(path, (1, 1))  # forza un mtime diverso
    assert lookup(CH) is None
    sync_to_db([], db)
    assert not db.get_channel(CH).enabled


def test_resolve_channel_ref():
    assert resolve_channel_ref(CH, lambda h: None) == (CH, "")
    assert resolve_channel_ref("@TradingFacile", lambda h: (CH, "TF")) == (CH, "TF")
    with pytest.raises(PermanentError):
        resolve_channel_ref("@Inesistente", lambda h: None)
    with pytest.raises(PermanentError):
        resolve_channel_ref("non è un canale", lambda h: None)


# --- monitor --------------------------------------------------------------------------------------
def _monitor(settings, db, routes, api_key=None):
    client = _client(routes)
    api = DataApi(api_key, client) if api_key else None
    return Monitor(settings, db, client=client, dataapi=api, pause_s=0)


def test_monitor_enqueues_new_videos(settings, db):
    append_channels(settings.channels_file, [ChannelConfig(id=CH, name="Trading Facile")])
    mon = _monitor(settings, db, lambda r: httpx.Response(200, content=FEED))
    stats = mon.poll(now=NOW)
    assert stats.new_videos == ["newvideo001", "newvideo002"]  # niente Short, niente video vecchi
    assert stats.skipped_shorts == 1 and stats.channels_ok == 1
    row = db.get_video("newvideo001")
    assert row.status == VideoStatus.QUEUED and row.source == "rss" and row.title == "BTC: settimana decisiva"
    assert mon.poll(now=NOW).new_videos == []  # nessun duplicato
    assert db.get_channel(CH).last_poll_ok is True


def test_monitor_falls_back_to_dataapi_when_rss_fails(settings, db):
    append_channels(settings.channels_file, [ChannelConfig(id=CH, name="Trading Facile")])

    def routes(request):
        if "youtube.com/feeds" in str(request.url):
            return httpx.Response(404)
        return httpx.Response(200, json=_uploads_json())

    stats = _monitor(settings, db, routes, api_key="KEY").poll(now=NOW)
    assert stats.used_fallback == 1 and stats.new_videos == ["apivideo001"]


def test_monitor_records_failure_without_fallback(settings, db):
    append_channels(settings.channels_file, [ChannelConfig(id=CH, name="Trading Facile")])
    stats = _monitor(settings, db, lambda r: httpx.Response(500)).poll(now=NOW)
    assert stats.channels_failed == 1 and "500" in stats.errors[0]
    assert db.get_channel(CH).last_poll_ok is False


def test_monitor_watch_playlist(home):
    s = load_settings(home, overrides={"monitor": {"watch_playlists": ["PLdariassumere"]}})
    s.ensure_dirs()
    database = open_db(s.db_path)
    seen = []

    def routes(request):
        seen.append(str(request.url))
        return httpx.Response(200, content=FEED)

    stats = _monitor(s, database, routes).poll(now=NOW)
    assert any("playlist_id=PLdariassumere" in u for u in seen)
    assert "oldvideo001" in stats.new_videos and "shortvid001" in stats.new_videos  # scelta tua: nessun filtro
    assert database.get_video("oldvideo001").source == "playlist"


# --- demone -------------------------------------------------------------------------------------
class _FakeMonitor:
    def __init__(self, fail=False):
        self.calls, self.fail = 0, fail

    def poll(self, now=None):
        self.calls += 1
        if self.fail:
            raise RuntimeError("rete giù")


class _FakePipeline:
    def __init__(self, items=1):
        self.items = items

    def run_next(self):
        if self.items:
            self.items -= 1
            return object()
        return None


def test_daemon_tick_polls_on_schedule_and_works_queue(settings, db):
    from ytkb.daemon import Daemon

    clock = {"now": NOW}
    mon = _FakeMonitor()
    d = Daemon(settings, db, pipeline=_FakePipeline(items=1), monitor=mon, clock=lambda: clock["now"])
    assert d.tick() is True and mon.calls == 1
    assert d.tick() is False and mon.calls == 1  # coda vuota, polling non ancora dovuto
    clock["now"] += timedelta(minutes=16)
    d.tick()
    assert mon.calls == 2
    assert db.kv_get("daemon_heartbeat").startswith("2026-10-27T10:16")


def test_daemon_survives_errors_and_stops(settings, db):
    from ytkb.daemon import Daemon

    d = Daemon(settings, db, pipeline=_FakePipeline(items=0), monitor=_FakeMonitor(fail=True), idle_sleep_s=0.01)
    t = threading.Thread(target=d.run_forever)
    t.start()
    d.stop_event.wait(0.1)
    d.stop_event.set()
    t.join(timeout=5)
    assert not t.is_alive()


def test_settings_json_roundtrip(settings):
    json.dumps(settings.model_dump(mode="json"))  # la configurazione è serializzabile
