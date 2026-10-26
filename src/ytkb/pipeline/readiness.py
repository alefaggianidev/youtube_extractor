"""Il video è pronto per essere analizzato? (stadio 1, dopo i metadati)"""

from __future__ import annotations

from datetime import datetime

from ytkb.config import FilterSettings
from ytkb.errors import NotReadyError, SkipError
from ytkb.models import LiveStatus, VideoMeta
from ytkb.utils.text import fmt_duration

NOT_ACCESSIBLE = {"private", "subscriber_only", "premium_only", "needs_auth"}


def check_readiness(meta: VideoMeta, filters: FilterSettings, *, manual: bool, now: datetime) -> None:
    """Solleva ``SkipError`` (da scartare) o ``NotReadyError`` (da riprovare più tardi); altrimenti non fa nulla.

    Per le richieste manuali (CLI, Telegram) i filtri di durata e Shorts non si applicano: le hai chieste tu.
    """
    if meta.availability in NOT_ACCESSIBLE:
        raise SkipError(f"video non accessibile ({meta.availability})")
    if meta.live_status == LiveStatus.IS_UPCOMING:
        if meta.release_at and meta.release_at > now:
            minutes = (meta.release_at - now).total_seconds() / 60 + 10
            raise NotReadyError(f"premiere/diretta programmata alle {meta.release_at:%Y-%m-%d %H:%M} UTC",
                                retry_after_minutes=max(10.0, minutes))
        raise NotReadyError("premiere/diretta in arrivo", retry_after_minutes=20)
    if meta.live_status == LiveStatus.IS_LIVE:
        if filters.live_policy == "skip" and not manual:
            raise SkipError("diretta (live_policy: skip)")
        raise NotReadyError("diretta in corso: aspetto che finisca", retry_after_minutes=30)
    if meta.live_status == LiveStatus.POST_LIVE:
        raise NotReadyError("diretta appena terminata: YouTube sta elaborando la registrazione", retry_after_minutes=30)
    if manual:
        return
    if filters.skip_shorts and meta.is_short:
        raise SkipError("Short")
    if meta.duration_s:
        if meta.duration_s < filters.min_duration_s:
            raise SkipError(f"troppo corto ({fmt_duration(meta.duration_s)})")
        if meta.duration_s > filters.max_duration_s:
            raise SkipError(f"troppo lungo ({fmt_duration(meta.duration_s)}, massimo "
                            f"{fmt_duration(filters.max_duration_s)})")
