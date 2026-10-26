from datetime import timedelta

from ytkb.models import VideoStatus
from ytkb.utils.timeutil import to_iso


def test_migrate_is_idempotent(db):
    assert db.migrate() == 1
    assert db.migrate() == 1


def test_add_and_claim_respects_priority_and_time(db, fixed_now):
    assert db.add_video("aaaaaaaaaaa", source="rss", title="auto", now=fixed_now)
    assert db.add_video("bbbbbbbbbbb", source="manual", title="manuale", priority=10, now=fixed_now)
    assert not db.add_video("aaaaaaaaaaa", source="rss", now=fixed_now)  # duplicato ignorato

    first = db.claim_next_due(now=fixed_now)
    assert first.video_id == "bbbbbbbbbbb"
    assert first.status == VideoStatus.PROCESSING
    second = db.claim_next_due(now=fixed_now)
    assert second.video_id == "aaaaaaaaaaa"
    assert db.claim_next_due(now=fixed_now) is None


def test_waiting_video_is_claimed_only_when_due(db, fixed_now):
    db.add_video("ccccccccccc", source="rss", now=fixed_now)
    later = fixed_now + timedelta(minutes=30)
    db.update_video("ccccccccccc", status=VideoStatus.WAITING, next_attempt_at=to_iso(later))
    assert db.claim_next_due(now=fixed_now) is None
    assert db.claim_next_due(now=later).video_id == "ccccccccccc"


def test_release_stale(db, fixed_now):
    db.add_video("ddddddddddd", source="rss", now=fixed_now)
    db.claim_next_due(now=fixed_now)
    assert db.release_stale(90, now=fixed_now + timedelta(minutes=10)) == 0
    assert db.release_stale(90, now=fixed_now + timedelta(minutes=120)) == 1
    assert db.get_video("ddddddddddd").status == VideoStatus.QUEUED


def test_llm_costs_accumulate(db, fixed_now):
    db.add_video("eeeeeeeeeee", source="manual", now=fixed_now)
    for _ in range(2):
        db.record_llm_call(video_id="eeeeeeeeeee", purpose="analysis", model="m", service_tier="flex",
                           input_tokens=1000, output_tokens=100, thought_tokens=10, video_tokens=0,
                           cost_usd=0.01, now=fixed_now)
    assert abs(db.get_video("eeeeeeeeeee").cost_usd - 0.02) < 1e-9
    assert abs(db.llm_cost_since(fixed_now - timedelta(hours=1)) - 0.02) < 1e-9
    assert db.llm_cost_since(fixed_now + timedelta(hours=1)) == 0


def test_channels_and_kv(db):
    db.upsert_channel("UCBR8-60-B28hp2BmDPdntcQ", title="YouTube")
    db.upsert_channel("UCBR8-60-B28hp2BmDPdntcQ", title="", handle="@YouTube")
    ch = db.get_channel("UCBR8-60-B28hp2BmDPdntcQ")
    assert ch.title == "YouTube" and ch.handle == "@YouTube" and ch.enabled
    db.mark_channel_polled(ch.channel_id, ok=False, error="404")
    assert db.get_channel(ch.channel_id).last_poll_ok is False
    db.kv_set("telegram_offset", "42")
    assert db.kv_get("telegram_offset") == "42"
    assert db.kv_get("manca", "default") == "default"
