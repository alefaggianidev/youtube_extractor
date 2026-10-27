"""Messaggio breve per Telegram (HTML semplificato), costruito dal view-model del report."""

from __future__ import annotations

from html import escape

from ytkb.report.viewmodel import ReportVM
from ytkb.utils.text import truncate

MAX_MESSAGE = 4000  # limite Telegram 4096


def _e(text: object) -> str:
    return escape(str(text or ""), quote=False)


def summary_html(vm: ReportVM) -> str:
    lines = [f"📈 <b>{_e(vm.title)}</b>",
             f"<i>{_e(vm.channel)}</i> · {_e(vm.duration)} · <a href=\"{_e(vm.video_url)}\">YouTube</a>"]
    if vm.is_demo:
        lines.append("⚠️ <i>Report dimostrativo (senza AI)</i>")
    lines += ["", "⚡ <b>In 30 secondi</b>"]
    lines += [f"• {_e(p)}" for p in vm.tldr]
    lines += ["", f"🎯 <b>Vale la pena?</b> {vm.worth_stars} — {_e(truncate(vm.worth_reason, 200))}"]
    for rg in vm.worth_ranges[:3]:
        lines.append(f"▶ <a href=\"{_e(rg.url)}\">{_e(rg.label)}</a> {_e(truncate(rg.reason, 80))}")
    if vm.assets:
        lines.append("")
        for a in vm.assets[:6]:
            levels = ", ".join(f"{_e(lv.kind.lower())} {_e(lv.value)} {lv.badge}" for lv in a.levels[:4])
            tf = f" ({_e(a.timeframe)})" if a.timeframe else ""
            lines.append(f"{a.bias_emoji} <b>{_e(a.asset)}</b> {_e(a.bias_label)}{tf}" + (f": {levels}" if levels else ""))
    for s in vm.sponsor[:2]:
        lines.append(f"💼 {_e(truncate(s, 120))}")
    text = "\n".join(lines)
    if len(text) > MAX_MESSAGE:
        text = text[: MAX_MESSAGE - 20].rsplit("\n", 1)[0] + "\n…"
    return text
