from datetime import timedelta

import pytest

from tests.helpers import FIXTURES, StaticSource, btc_snippets, load_json, video_meta
from ytkb.errors import BlockedError, NotReadyError, PermanentError, TemporaryError
from ytkb.youtube.transcripts import (
    RawSnippet,
    TrackInfo,
    TranscriptApiSource,
    TranscriptService,
    TranscriptUnavailable,
    build_segments,
    captions_wait_minutes,
    parse_json3,
    pick_track,
    pick_ytdlp_lang,
)


def test_pick_track_prefers_manual_in_original_language():
    tracks = [TrackInfo("en", False), TrackInfo("it", True), TrackInfo("it", False)]
    assert pick_track(tracks, "it", ["it", "en"]) == 2


def test_pick_track_prefers_original_auto_over_translated_manual():
    tracks = [TrackInfo("en", False), TrackInfo("it", True)]
    assert pick_track(tracks, None, ["en"]) == 1  # la traccia automatica indica la lingua parlata


def test_pick_track_falls_back():
    assert pick_track([TrackInfo("de", False)], "it", ["it"]) == 0
    assert pick_track([], "it", ["it"]) is None


def test_parse_json3_joins_segments_and_skips_noise():
    data = load_json("subs_sample.json3")
    snippets = parse_json3(data)
    assert [s.text for s in snippets] == ["ciao a tutti e benvenuti", "oggi parliamo di bitcoin", "[Musica]"]
    assert snippets[1].start == 5.2


def test_pick_ytdlp_lang():
    m = video_meta()
    assert pick_ytdlp_lang(m, ["it"]) == ("it-orig", True)
    manual = m.model_copy(update={"subtitle_langs": ["it"], "auto_caption_langs": []})
    assert pick_ytdlp_lang(manual, ["it"]) == ("it", False)
    assert pick_ytdlp_lang(m.model_copy(update={"auto_caption_langs": [], "subtitle_langs": []}), ["it"]) is None


def test_build_segments_merges_and_numbers():
    segs = build_segments(btc_snippets(), target_s=20, max_s=40)
    assert [s.id for s in segs] == list(range(1, len(segs) + 1))
    assert 3 <= len(segs) <= 8
    assert all(b.start >= a.end for a, b in zip(segs, segs[1:], strict=False))  # niente sovrapposizioni
    assert all(s.end - s.start <= 40 for s in segs)
    assert "[Musica]" not in " ".join(s.text for s in segs)
    assert segs[0].start == 0.0


def test_build_segments_breaks_at_sentence_end():
    snippets = [RawSnippet(0, 12, "prima frase lunga."), RawSnippet(12, 10, "seconda frase."),
                RawSnippet(22, 5, "terza")]
    segs = build_segments(snippets, target_s=20, max_s=40)
    assert [s.text for s in segs] == ["prima frase lunga. seconda frase.", "terza"]


def test_captions_wait_schedule():
    assert captions_wait_minutes([20, 40, 60, 120], 5) == 15
    assert captions_wait_minutes([20, 40, 60, 120], 30) == 30
    assert captions_wait_minutes([20, 40, 60, 120], 250) is None


# --- servizio con fonti finte ------------------------------------------------------------
def _service(settings, **sources):
    return TranscriptService(settings, sources)


def test_service_uses_first_working_source(settings, fixed_now):
    first = StaticSource("transcript_api", btc_snippets())
    second = StaticSource("ytdlp_subs", btc_snippets())
    t = _service(settings, transcript_api=first, ytdlp_subs=second).get(video_meta(), now=fixed_now)
    assert t.source == "transcript_api" and first.calls == 1 and second.calls == 0
    assert t.language == "it" and t.segments


def test_service_falls_back_to_second_source(settings, fixed_now):
    first = StaticSource("transcript_api", None)
    second = StaticSource("ytdlp_subs", btc_snippets())
    t = _service(settings, transcript_api=first, ytdlp_subs=second).get(video_meta(), now=fixed_now)
    assert t.source == "ytdlp_subs"


def test_service_waits_for_captions_on_fresh_video(settings):
    meta = video_meta()
    now = meta.published_at + timedelta(minutes=30)
    gemini = StaticSource("gemini_url", btc_snippets())
    svc = _service(settings, transcript_api=StaticSource("transcript_api", None), gemini_url=gemini)
    with pytest.raises(NotReadyError) as exc:
        svc.get(meta, now=now)
    assert exc.value.retry_after_minutes == 30
    assert gemini.calls == 0  # la fonte a pagamento non viene usata mentre aspettiamo
    # richiesta manuale: niente attesa
    assert svc.get(meta, now=now, allow_wait=False).source == "gemini_url"


def test_service_uses_gemini_immediately_when_blocked(settings):
    meta = video_meta()
    now = meta.published_at + timedelta(minutes=5)
    gemini = StaticSource("gemini_url", btc_snippets())
    svc = _service(settings, transcript_api=StaticSource("transcript_api", error=BlockedError("ip")),
                   gemini_url=gemini)
    assert svc.get(meta, now=now).source == "gemini_url"


def test_service_skips_gemini_for_unlisted_video(settings, fixed_now):
    meta = video_meta(availability="unlisted")
    gemini = StaticSource("gemini_url", btc_snippets())
    svc = _service(settings, transcript_api=StaticSource("transcript_api", None), gemini_url=gemini)
    with pytest.raises(PermanentError):
        svc.get(meta, now=fixed_now)
    assert gemini.calls == 0


def test_service_error_types(settings, fixed_now):
    meta = video_meta()
    blocked = _service(settings, transcript_api=StaticSource("transcript_api", error=BlockedError("x")))
    with pytest.raises(BlockedError):
        blocked.get(meta, now=fixed_now)
    temp = _service(settings, transcript_api=StaticSource("transcript_api", error=TemporaryError("rete")))
    with pytest.raises(TemporaryError):
        temp.get(meta, now=fixed_now)


# --- adattatore youtube-transcript-api con un finto client ---------------------------------
class _FakeTrack:
    def __init__(self, code, generated, snippets=None, error=None):
        self.language_code = code
        self.is_generated = generated
        self._snippets = snippets or []
        self._error = error

    def fetch(self):
        if self._error:
            raise self._error

        class _Fetched:
            pass

        f = _Fetched()
        f.language_code, f.is_generated = self.language_code, self.is_generated
        f.snippets = [type("S", (), {"start": s.start, "duration": s.duration, "text": s.text})() for s in
                      self._snippets]
        return f


class _FakeApi:
    def __init__(self, tracks=None, error=None):
        self._tracks, self._error = tracks or [], error

    def list(self, video_id):
        if self._error:
            raise self._error
        return self._tracks


def test_transcript_api_source_maps_results_and_errors(settings):
    import youtube_transcript_api as yta

    meta = video_meta()
    ok = TranscriptApiSource(settings, api_factory=lambda: _FakeApi([_FakeTrack("it", True, btc_snippets())]))
    raw = ok.fetch(meta, ["it"])
    assert raw.language == "it" and raw.is_generated and len(raw.snippets) == 20

    blocked = TranscriptApiSource(settings, api_factory=lambda: _FakeApi(error=yta.IpBlocked(meta.video_id)))
    with pytest.raises(BlockedError):
        blocked.fetch(meta, ["it"])
    disabled = TranscriptApiSource(settings, api_factory=lambda: _FakeApi(error=yta.TranscriptsDisabled(meta.video_id)))
    with pytest.raises(TranscriptUnavailable):
        disabled.fetch(meta, ["it"])
    empty = TranscriptApiSource(settings, api_factory=lambda: _FakeApi([]))
    with pytest.raises(TranscriptUnavailable):
        empty.fetch(meta, ["it"])


def test_fixture_files_exist():
    assert (FIXTURES / "subs_sample.json3").exists()
