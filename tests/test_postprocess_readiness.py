from datetime import timedelta

import pytest

from tests.helpers import analysis_for, btc_snippets, video_meta
from ytkb.config import FilterSettings
from ytkb.errors import NotReadyError, SkipError
from ytkb.llm.schemas import AnalysisResult, PriceLevel
from ytkb.models import Transcript
from ytkb.pipeline.postprocess import level_provenance, postprocess_analysis
from ytkb.pipeline.readiness import check_readiness
from ytkb.youtube.transcripts import build_segments


@pytest.fixture
def transcript() -> Transcript:
    return Transcript(video_id="dQw4w9WgXcQ", language="it", source="transcript_api",
                      segments=build_segments(btc_snippets(), 8, 14))


def test_postprocess_clamps_and_limits(transcript):
    raw = AnalysisResult.model_validate(analysis_for(transcript))
    r = postprocess_analysis(raw, transcript, max_triggers=8)
    slide = [t for t in r.visual_triggers if t.trigger_type == "EDUCATIONAL_SLIDE"][0]
    assert slide.end_segment <= transcript.last_id  # ID fuori intervallo corretto
    assert slide.end_segment - slide.start_segment <= 2
    assert r.assets[0].asset == "BTCUSD"  # ticker normalizzato
    assert [c.title for c in r.chapters].count("Doppione") == 0  # capitolo duplicato rimosso
    only_one = postprocess_analysis(raw, transcript, max_triggers=1)
    assert len(only_one.visual_triggers) == 1 and only_one.visual_triggers[0].importance == 5


def test_level_provenance(transcript):
    r = AnalysisResult.model_validate(analysis_for(transcript))
    support, target, invented = r.assets[0].levels
    assert level_provenance(support, transcript) == "spoken"
    assert level_provenance(target, transcript) == "spoken"
    assert level_provenance(invented, transcript) == "unverified"
    # anche senza spoken_text basta il numero nel segmento
    bare = PriceLevel(value=60000, kind="SUPPORT", segment_id=support.segment_id, spoken_text="")
    assert level_provenance(bare, transcript) == "spoken"


def test_readiness_rules(fixed_now):
    f = FilterSettings()
    check_readiness(video_meta(duration=600), f, manual=False, now=fixed_now)  # ok
    with pytest.raises(SkipError, match="Short"):
        check_readiness(video_meta("ytdlp_info_short.json"), f, manual=False, now=fixed_now)
    check_readiness(video_meta("ytdlp_info_short.json"), f, manual=True, now=fixed_now)  # manuale: ok
    with pytest.raises(SkipError, match="troppo corto"):
        check_readiness(video_meta(duration=60), f, manual=False, now=fixed_now)
    with pytest.raises(SkipError, match="troppo lungo"):
        check_readiness(video_meta(duration=5 * 3600), f, manual=False, now=fixed_now)
    with pytest.raises(SkipError, match="non accessibile"):
        check_readiness(video_meta(availability="subscriber_only"), f, manual=True, now=fixed_now)


def test_readiness_live_and_premiere(fixed_now):
    f = FilterSettings()
    up = video_meta("ytdlp_info_upcoming.json")
    with pytest.raises(NotReadyError) as exc:
        check_readiness(up, f, manual=False, now=fixed_now)
    assert exc.value.retry_after_minutes == pytest.approx(250)  # 4 ore alla premiere + 10 minuti
    with pytest.raises(NotReadyError):
        check_readiness(video_meta(live_status="is_live"), f, manual=False, now=fixed_now)
    with pytest.raises(SkipError):
        check_readiness(video_meta(live_status="is_live"), FilterSettings(live_policy="skip"), manual=False,
                        now=fixed_now)
    with pytest.raises(NotReadyError):
        check_readiness(video_meta(live_status="post_live"), f, manual=False,
                        now=fixed_now + timedelta(hours=1))
