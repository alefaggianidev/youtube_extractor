"""Caricamento dei prompt (file ``prompts/*.md``, template Jinja2)."""

from __future__ import annotations

from functools import lru_cache

from jinja2 import Environment, PackageLoader, StrictUndefined


@lru_cache(maxsize=1)
def _env() -> Environment:
    return Environment(
        loader=PackageLoader("ytkb.llm", "prompts"),
        undefined=StrictUndefined,
        keep_trailing_newline=False,
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,
    )


def render_prompt(name: str, **context: object) -> str:
    return _env().get_template(f"{name}.md").render(**context).strip()
