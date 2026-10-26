import pytest

from ytkb.youtube.urls import (
    extract_video_id,
    find_video_ids,
    parse_channel_ref,
    timestamp_url,
    uploads_playlist_id,
)

VID = "dQw4w9WgXcQ"


@pytest.mark.parametrize("text", [
    VID,
    f"https://youtu.be/{VID}",
    f"https://youtu.be/{VID}?t=42",
    f"https://www.youtube.com/watch?v={VID}",
    f"https://www.youtube.com/watch?v={VID}&list=PL123&index=2",
    f"https://m.youtube.com/watch?v={VID}",
    f"https://www.youtube.com/shorts/{VID}",
    f"https://www.youtube.com/live/{VID}?si=abc",
    f"https://www.youtube.com/embed/{VID}",
    f"www.youtube.com/watch?v={VID}",
    f"https://music.youtube.com/watch?v={VID}",
])
def test_extract_video_id(text):
    assert extract_video_id(text) == VID


@pytest.mark.parametrize("text", ["", "ciao", "https://vimeo.com/123", "https://www.youtube.com/@canale",
                                  "https://youtu.be/troppo-corto"])
def test_extract_video_id_rejects(text):
    assert extract_video_id(text) is None


def test_find_video_ids_in_message():
    msg = f"guarda questo https://youtu.be/{VID} e anche (https://www.youtube.com/watch?v=abcdefghijk)."
    assert find_video_ids(msg) == [VID, "abcdefghijk"]


def test_timestamp_url():
    assert timestamp_url(VID, 792.7) == f"https://youtu.be/{VID}?t=792"


def test_parse_channel_ref():
    assert parse_channel_ref("@TradingFacile") == ("handle", "@TradingFacile")
    assert parse_channel_ref("https://www.youtube.com/@TradingFacile/videos") == ("handle", "@TradingFacile")
    assert parse_channel_ref("UCBR8-60-B28hp2BmDPdntcQ") == ("id", "UCBR8-60-B28hp2BmDPdntcQ")
    assert parse_channel_ref("https://www.youtube.com/channel/UCBR8-60-B28hp2BmDPdntcQ") == (
        "id", "UCBR8-60-B28hp2BmDPdntcQ")
    assert parse_channel_ref("https://www.youtube.com/c/Vecchio") == ("url", "https://www.youtube.com/c/Vecchio")
    assert parse_channel_ref("https://example.com/@x") is None


def test_uploads_playlist_id():
    assert uploads_playlist_id("UCBR8-60-B28hp2BmDPdntcQ") == "UUBR8-60-B28hp2BmDPdntcQ"
