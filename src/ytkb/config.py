"""Configurazione: ``config/settings.yaml`` + segreti da ``.env`` / variabili d'ambiente.

Ogni chiave del YAML è facoltativa (vale il default qui sotto). Le chiavi sconosciute danno errore:
così un refuso nel file di configurazione non passa inosservato.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from ytkb.errors import ConfigError

TranscriptSourceName = Literal["transcript_api", "ytdlp_subs", "gemini_url"]


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PathsSettings(_Section):
    data_dir: Path = Path("data")
    archive_dir: Path | None = None  # default: <data_dir>/archive


class ReportSettings(_Section):
    language: str = "it"
    timezone: str = "Europe/Rome"


class ModelPrice(_Section):
    input: float
    output: float


class LLMModels(_Section):
    analysis: str = "gemini-3.8-flash"
    visual: str = "gemini-3.8-flash"
    transcribe: str = "gemini-3.8-flash"


def _default_pricing() -> dict[str, ModelPrice]:
    return {
        "gemini-3.8-flash": ModelPrice(input=0.75, output=3.75),
        "gemini-3.6-flash": ModelPrice(input=0.75, output=3.75),
        "gemini-3.5-flash-lite": ModelPrice(input=0.30, output=2.50),
    }


class LLMSettings(_Section):
    provider: Literal["gemini", "fake"] = "gemini"
    models: LLMModels = Field(default_factory=LLMModels)
    service_tier: Literal["flex", "standard", "priority"] = "flex"
    flex_fallback_to_standard: bool = True
    thinking_level: Literal["minimal", "low", "medium", "high"] = "low"
    max_output_tokens: int = 16000
    request_timeout_s: float = 600
    daily_budget_usd: float = 2.0
    count_youtube_input_as_paid: bool = True
    pricing: dict[str, ModelPrice] = Field(default_factory=_default_pricing)


class TranscriptSettings(_Section):
    languages: list[str] = Field(default_factory=lambda: ["it", "en"])
    sources: list[TranscriptSourceName] = Field(
        default_factory=lambda: ["transcript_api", "ytdlp_subs", "gemini_url"]
    )
    wait_for_captions_minutes: list[float] = Field(default_factory=lambda: [20, 40, 60, 120])
    segment_target_s: float = 20
    segment_max_s: float = 40
    gemini_chunk_minutes: int = 30


class VisualSettings(_Section):
    enabled: bool = True
    max_triggers: int = 8
    locate: bool = True
    locate_padding_s: float = 3
    locate_fps: float = 1.0
    read_frame: bool = True
    capture: bool = True
    capture_height: int = 1080
    capture_window_s: float = 1.5
    frames_per_trigger: int = 3
    clips: bool = False
    clip_max_s: float = 30
    parallel_requests: int = 4


class FilterSettings(_Section):
    skip_shorts: bool = True
    min_duration_s: int = 120
    max_duration_s: int = 10800
    live_policy: Literal["wait", "skip"] = "wait"

    def merged(self, overrides: dict[str, Any] | None) -> FilterSettings:
        """Applica i filtri specifici di un canale sopra quelli generali."""
        if not overrides:
            return self
        return FilterSettings.model_validate({**self.model_dump(), **overrides})


class MonitorSettings(_Section):
    poll_interval_minutes: float = 15
    rss_enabled: bool = True
    dataapi_fallback: bool = True
    lookback_hours: float = 48


class YtdlpSettings(_Section):
    cookies_file: str = ""
    extractor_args: dict[str, dict[str, list[str]]] = Field(default_factory=dict)
    sleep_requests_s: float = 1.0
    auto_update: bool = True
    deno_path: str = ""  # vuoto = ricerca automatica (PATH e ambiente Python)


class TelegramSettings(_Section):
    enabled: bool = False
    allowed_chat_ids: list[int] = Field(default_factory=list)
    send_html_report: bool = True
    notify_on_failure: bool = True


class WorkerSettings(_Section):
    max_attempts: int = 5
    retry_backoff_minutes: list[float] = Field(default_factory=lambda: [5, 15, 60, 180, 720])
    stale_processing_minutes: float = 90


class LoggingSettings(_Section):
    level: str = "INFO"


class Secrets(BaseSettings):
    """Segreti letti da variabili d'ambiente e, se presente, dal file ``.env``."""

    model_config = SettingsConfigDict(extra="ignore", env_file_encoding="utf-8")

    gemini_api_key: SecretStr | None = None
    youtube_api_key: SecretStr | None = None
    telegram_bot_token: SecretStr | None = None
    ytkb_proxy: SecretStr | None = None

    def values_to_redact(self) -> list[str]:
        out = []
        for field in ("gemini_api_key", "youtube_api_key", "telegram_bot_token", "ytkb_proxy"):
            value = getattr(self, field)
            if value is not None and value.get_secret_value():
                out.append(value.get_secret_value())
        return out

    @staticmethod
    def reveal(value: SecretStr | None) -> str:
        return value.get_secret_value() if value is not None else ""


class Settings(_Section):
    paths: PathsSettings = Field(default_factory=PathsSettings)
    report: ReportSettings = Field(default_factory=ReportSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    transcript: TranscriptSettings = Field(default_factory=TranscriptSettings)
    visual: VisualSettings = Field(default_factory=VisualSettings)
    filters: FilterSettings = Field(default_factory=FilterSettings)
    monitor: MonitorSettings = Field(default_factory=MonitorSettings)
    ytdlp: YtdlpSettings = Field(default_factory=YtdlpSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    worker: WorkerSettings = Field(default_factory=WorkerSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    _home: Path = PrivateAttr(default_factory=Path.cwd)
    _secrets: Secrets = PrivateAttr(default_factory=Secrets)
    _source: Path | None = PrivateAttr(default=None)

    # --- valori risolti ----------------------------------------------------------------
    @property
    def home(self) -> Path:
        return self._home

    @property
    def secrets(self) -> Secrets:
        return self._secrets

    @property
    def source_file(self) -> Path | None:
        return self._source

    def _resolve(self, p: Path) -> Path:
        return p if p.is_absolute() else (self._home / p).resolve()

    @property
    def data_dir(self) -> Path:
        return self._resolve(self.paths.data_dir)

    @property
    def archive_dir(self) -> Path:
        return self._resolve(self.paths.archive_dir) if self.paths.archive_dir else self.data_dir / "archive"

    @property
    def state_dir(self) -> Path:
        return self.data_dir / "state"

    @property
    def work_dir(self) -> Path:
        return self.data_dir / "work"

    @property
    def db_path(self) -> Path:
        return self.state_dir / "ytkb.db"

    @property
    def config_dir(self) -> Path:
        return self._home / "config"

    @property
    def channels_file(self) -> Path:
        return self.config_dir / "channels.yaml"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.archive_dir, self.state_dir, self.work_dir):
            d.mkdir(parents=True, exist_ok=True)


def find_home() -> Path:
    """Cartella del progetto: ``$YTKB_HOME`` oppure la cartella corrente."""
    env = os.environ.get("YTKB_HOME")
    return Path(env).expanduser().resolve() if env else Path.cwd().resolve()


def _format_validation_error(exc: ValidationError, source: Path | None) -> str:
    where = f" in {source}" if source else ""
    lines = [f"Configurazione non valida{where}:"]
    for err in exc.errors():
        loc = ".".join(str(x) for x in err["loc"])
        lines.append(f"  - {loc}: {err['msg']}")
    return "\n".join(lines)


def load_settings(
    home: Path | None = None,
    settings_file: Path | None = None,
    env_file: Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> Settings:
    """Carica la configurazione. Se ``config/settings.yaml`` non esiste usa i default."""
    home = (home or find_home()).resolve()
    settings_file = settings_file or home / "config" / "settings.yaml"
    raw: dict[str, Any] = {}
    source: Path | None = None
    if settings_file.exists():
        try:
            raw = yaml.safe_load(settings_file.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"Errore di sintassi YAML in {settings_file}: {exc}") from exc
        if not isinstance(raw, dict):
            raise ConfigError(f"{settings_file} deve contenere un dizionario YAML")
        source = settings_file
    if overrides:
        raw = _deep_merge(raw, overrides)
    try:
        settings = Settings.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(exc, source)) from exc
    env_file = env_file or home / ".env"
    settings._home = home
    settings._source = source
    settings._secrets = Secrets(_env_file=env_file if env_file.exists() else None)
    return settings


def _deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out
