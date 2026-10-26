from datetime import UTC, datetime

import pytest

from tests.helpers import load_json, video_meta
from ytkb.errors import BlockedError, NotReadyError, PermanentError, TemporaryError
from ytkb.models import LiveStatus
from ytkb.youtube.metadata import meta_from_info
from ytkb.youtube.ytdlp import classify_error


def test_meta_from_info_normal_video():
    m = video_meta()
    assert m.video_id == "dQw4w9WgXcQ"
    assert m.channel_title == "Trading Facile"
    assert m.channel_handle == "@TradingFacile"
    assert m.published_at == datetime(2026, 10, 26, 16, 2, tzinfo=UTC)
    assert m.duration_s == 118
    assert m.live_status == LiveStatus.NOT_LIVE
    assert not m.is_short and m.is_public
    assert [c.title for c in m.chapters] == ["Intro", "Bitcoin", "S&P 500", "Teoria: i supporti"]
    assert m.subtitle_langs == []  # live_chat non è un sottotitolo
    assert m.original_caption_lang == "it"


def test_meta_from_info_upcoming_and_short():
    up = meta_from_info(load_json("ytdlp_info_upcoming.json"))
    assert up.live_status == LiveStatus.IS_UPCOMING
    assert up.release_at == datetime(2026, 10, 27, 14, 0, tzinfo=UTC)
    assert up.duration_s is None
    short = meta_from_info(load_json("ytdlp_info_short.json"))
    assert short.is_short


def test_short_detected_from_shape_when_media_type_missing():
    info = load_json("ytdlp_info_short.json")
    info.pop("media_type")
    info["webpage_url"] = "https://www.youtube.com/watch?v=short123456"
    assert meta_from_info(info).is_short


def test_unknown_live_status_is_tolerated():
    assert video_meta(live_status="qualcosa_di_nuovo").live_status == LiveStatus.UNKNOWN


@pytest.mark.parametrize("message,expected", [
    ("ERROR: [youtube] abc: Sign in to confirm you're not a bot. Use --cookies", BlockedError),
    ("ERROR: [youtube] abc: Private video. Sign in if you've been granted access", PermanentError),
    ("ERROR: [youtube] abc: Join this channel to get access to members-only content", PermanentError),
    ("ERROR: [youtube] abc: Premieres in 3 hours", NotReadyError),
    ("ERROR: [youtube] abc: This live event will begin in 2 hours", NotReadyError),
    ("ERROR: unable to download webpage: HTTP Error 429: Too Many Requests", BlockedError),
    ("ERROR: Connection reset by peer", TemporaryError),
])
def test_classify_ytdlp_errors(message, expected):
    err = classify_error(RuntimeError(message))
    assert type(err) is expected
