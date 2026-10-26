"""Generazione dei file del report a partire dal view-model."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import yaml
from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from ytkb.report.images import to_data_uri
from ytkb.report.viewmodel import ReportVM

log = logging.getLogger(__name__)


def md_cell(text: object) -> str:
    """Testo sicuro dentro una cella di tabella Markdown."""
    return str(text or "").replace("|", "\\|").replace("\n", " ").strip()


def md_inline(text: object) -> str:
    """Testo su una riga (niente a capo che romperebbero elenchi e citazioni)."""
    return " ".join(str(text or "").split())


@lru_cache(maxsize=1)
def _env() -> Environment:
    env = Environment(
        loader=PackageLoader("ytkb.report", "templates"),
        undefined=StrictUndefined,
        autoescape=select_autoescape(enabled_extensions=("html.j2",), default_for_string=False),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["md_cell"] = md_cell
    env.filters["md_inline"] = md_inline
    return env


def render_markdown(vm: ReportVM) -> str:
    front = yaml.safe_dump(vm.frontmatter, allow_unicode=True, sort_keys=False, width=1000).strip()
    return _env().get_template("report.md.j2").render(r=vm, frontmatter=front).strip() + "\n"


def render_html(vm: ReportVM, embed_images: bool = True) -> str:
    images: dict[int, str] = {}
    if embed_images:
        for v in [*vm.other_visuals, *(v for a in vm.assets for v in a.visuals)]:
            if v.image_path:
                try:
                    images[v.number] = to_data_uri(v.image_path)
                except OSError as exc:  # immagine illeggibile: il report esce comunque
                    log.warning("Immagine non incorporabile %s: %s", v.image_path, exc)
    return _env().get_template("report.html.j2").render(r=vm, images=images)


def write_reports(vm: ReportVM, root: Path) -> tuple[Path, Path]:
    from ytkb.utils.fs import atomic_write_text

    md_path, html_path = root / "report.md", root / "report.html"
    atomic_write_text(md_path, render_markdown(vm))
    atomic_write_text(html_path, render_html(vm))
    return md_path, html_path
