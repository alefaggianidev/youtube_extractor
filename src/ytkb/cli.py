"""Interfaccia a riga di comando ``ytkb``."""

from __future__ import annotations

import contextlib
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ytkb import __version__
from ytkb.config import Settings, load_settings
from ytkb.db import Database, open_db
from ytkb.errors import ConfigError
from ytkb.logging_setup import setup_logging
from ytkb.models import Stage, VideoStatus
from ytkb.youtube.urls import extract_video_id

app = typer.Typer(
    help="yt-finance-kb: report in italiano dei video YouTube di finanza e trading.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

STATUS_LABELS = {
    "queued": "🕒 in coda",
    "waiting": "⏳ in attesa",
    "processing": "⚙️ in lavorazione",
    "done": "✅ fatto",
    "skipped": "⏭️ saltato",
    "failed": "❌ fallito",
}


@dataclass
class CliState:
    settings: Settings
    _db: Database | None = None

    @property
    def db(self) -> Database:
        if self._db is None:
            self.settings.ensure_dirs()
            self._db = open_db(self.settings.db_path)
        return self._db


def _state(ctx: typer.Context) -> CliState:
    return ctx.obj


@app.callback()
def _main(
    ctx: typer.Context,
    home: Path = typer.Option(None, "--home", envvar="YTKB_HOME", help="Cartella del progetto (default: corrente)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Log dettagliati."),
) -> None:
    settings = load_settings(home)
    setup_logging("DEBUG" if verbose else settings.logging.level, settings.secrets.values_to_redact())
    ctx.obj = CliState(settings=settings)


@app.command()
def version() -> None:
    """Mostra la versione."""
    console.print(f"ytkb {__version__}")


@app.command()
def init(ctx: typer.Context, force: bool = typer.Option(False, help="Sovrascrive i file esistenti.")) -> None:
    """Crea config/settings.yaml, config/channels.yaml, .env e le cartelle dati."""
    st = _state(ctx)
    home = st.settings.home
    pairs = [
        (home / "config" / "settings.example.yaml", home / "config" / "settings.yaml"),
        (home / "config" / "channels.example.yaml", home / "config" / "channels.yaml"),
        (home / ".env.example", home / ".env"),
    ]
    for src, dst in pairs:
        if dst.exists() and not force:
            console.print(f"• {dst.relative_to(home)} esiste già: lo lascio com'è")
            continue
        if not src.exists():
            console.print(f"[yellow]• manca {src.relative_to(home)}: non posso creare {dst.name}[/yellow]")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        if dst.name == ".env":
            with contextlib.suppress(OSError):
                dst.chmod(0o600)
        console.print(f"[green]• creato {dst.relative_to(home)}[/green]")
    settings = load_settings(home)
    settings.ensure_dirs()
    open_db(settings.db_path).close()
    console.print(f"[green]• cartelle dati e database pronti in {settings.data_dir}[/green]")
    console.print("Prossimi passi: inserisci GEMINI_API_KEY nel file .env, poi esegui `ytkb doctor`.")


@app.command()
def doctor(
    ctx: typer.Context,
    offline: bool = typer.Option(False, help="Salta i controlli di rete."),
) -> None:
    """Diagnostica dell'ambiente: dipendenze, chiavi, rete."""
    from ytkb.doctor import local_checks, network_checks

    st = _state(ctx)
    checks = local_checks(st.settings)
    if not offline:
        checks += network_checks(st.settings)
    table = Table(title="ytkb doctor", show_lines=False)
    table.add_column("Controllo")
    table.add_column("Esito")
    table.add_column("Dettaglio")
    failed = 0
    for c in checks:
        if c.ok:
            mark = "[green]OK[/green]"
        elif c.optional:
            mark = "[yellow]—[/yellow]"
        else:
            mark = "[red]KO[/red]"
            failed += 1
        detail = c.detail if c.ok or not c.hint else f"{c.detail}\n[dim]{c.hint}[/dim]"
        table.add_row(c.name, mark, detail)
    console.print(table)
    if failed:
        console.print(f"[red]{failed} controlli non superati.[/red]")
        raise typer.Exit(1)
    console.print("[green]Tutto pronto.[/green]")


@app.command()
def add(
    ctx: typer.Context,
    urls: list[str] = typer.Argument(..., help="Uno o più link YouTube (o ID video)."),
    force: bool = typer.Option(False, "--force", help="Rimette in coda anche se già processato."),
    now: bool = typer.Option(False, "--now", help="Processa subito, senza aspettare il demone."),
) -> None:
    """Mette in coda uno o più video (priorità alta). Con --now li processa subito."""
    st = _state(ctx)
    queued: list[str] = []
    for url in urls:
        vid = extract_video_id(url)
        if not vid:
            console.print(f"[red]Link non riconosciuto: {url}[/red]")
            continue
        if st.db.add_video(vid, source="manual", priority=10):
            console.print(f"[green]In coda: {vid}[/green]")
            queued.append(vid)
        else:
            row = st.db.get_video(vid)
            if force or (row and row.status in (VideoStatus.FAILED, VideoStatus.SKIPPED)):
                st.db.requeue(vid, priority=10)
                console.print(f"[green]Rimesso in coda: {vid}[/green]")
                queued.append(vid)
            elif row and row.status in (VideoStatus.QUEUED, VideoStatus.WAITING) and now:
                queued.append(vid)
            else:
                console.print(f"Già presente: {vid} ({STATUS_LABELS.get(row.status, row.status) if row else '?'}). "
                              "Usa --force per rifarlo.")
    if now and queued:
        pipeline = _build_pipeline(st)
        for vid in queued:
            console.print(f"⚙️  Elaboro {vid}…")
            _print_outcome(pipeline.process_now(vid, force_from=Stage.METADATA if force else None))


@app.command()
def status(
    ctx: typer.Context,
    limit: int = typer.Option(20, help="Quanti video mostrare."),
    only: str = typer.Option(None, "--status", help="Filtra per stato (queued, waiting, done, failed...)."),
) -> None:
    """Stato della coda e degli ultimi video."""
    st = _state(ctx)
    counts = st.db.count_by_status()
    summary = "  ".join(f"{STATUS_LABELS.get(k, k)}: {v}" for k, v in sorted(counts.items())) or "nessun video"
    console.print(summary)
    rows = st.db.list_videos(limit=limit, status=only)
    if not rows:
        return
    table = Table(show_lines=False)
    for col in ("Video", "Titolo", "Canale", "Stato", "Stadio", "Tent.", "Nota"):
        table.add_column(col)
    for r in rows:
        note = r.skip_reason or (r.last_error or "")
        table.add_row(r.video_id, (r.title or "")[:50], (r.channel_title or "")[:24],
                      STATUS_LABELS.get(r.status, r.status), r.stage or "", str(r.attempts), note[:60])
    console.print(table)


@app.command()
def retry(ctx: typer.Context, video_id: str = typer.Argument(..., help="ID o link del video.")) -> None:
    """Rimette in coda un video fallito o saltato."""
    st = _state(ctx)
    vid = extract_video_id(video_id) or video_id
    if not st.db.get_video(vid):
        console.print(f"[red]Video sconosciuto: {vid}[/red]")
        raise typer.Exit(1)
    st.db.requeue(vid, priority=10)
    console.print(f"[green]Rimesso in coda: {vid}[/green]")


@app.command()
def show(ctx: typer.Context, video_id: str = typer.Argument(..., help="ID o link del video.")) -> None:
    """Dettagli di un video ed eventi recenti."""
    st = _state(ctx)
    vid = extract_video_id(video_id) or video_id
    row = st.db.get_video(vid)
    if not row:
        console.print(f"[red]Video sconosciuto: {vid}[/red]")
        raise typer.Exit(1)
    for key, value in row.__dict__.items():
        if value not in (None, ""):
            console.print(f"[bold]{key}[/bold]: {value}")
    events = st.db.events_of(vid, limit=20)
    if events:
        console.print("\n[bold]Eventi recenti[/bold]")
        for e in reversed(events):
            console.print(f"{e['ts']} {e['level']:<7} {e['stage'] or '':<10} {e['message']}")


def _build_pipeline(st: CliState):
    """Costruisce la pipeline con gli adapter reali (i test la sostituiscono)."""
    from ytkb.pipeline.context import build_context
    from ytkb.pipeline.runner import Pipeline

    return Pipeline(build_context(st.settings, st.db))


def _print_outcome(row) -> None:
    label = STATUS_LABELS.get(row.status, row.status)
    title = row.title or row.video_id
    if row.status == VideoStatus.DONE:
        console.print(f"[green]{label} {title}[/green]\n   📄 {row.archive_dir}/report.md\n   🌐 {row.archive_dir}/report.html")
    elif row.status == VideoStatus.WAITING:
        console.print(f"[yellow]{label} {title}: {row.last_error}[/yellow]\n   Riprovo da solo con `ytkb run` "
                      "(oppure rilancia `ytkb process`).")
    elif row.status == VideoStatus.QUEUED:
        console.print(f"[yellow]⚠️ {title}: errore temporaneo, riprovo più tardi.\n   {row.last_error}[/yellow]")
    elif row.status == VideoStatus.SKIPPED:
        console.print(f"{label} {title}: {row.skip_reason}")
    else:
        console.print(f"[red]{label} {title}: {row.last_error}[/red]")


@app.command()
def process(
    ctx: typer.Context,
    video: str = typer.Argument(None, help="ID o link di un video specifico (default: tutti quelli in scadenza)."),
    from_stage: Stage = typer.Option(None, "--from", help="Rifà la pipeline da questo stadio in poi."),
    max_items: int = typer.Option(None, "--max", help="Numero massimo di video da lavorare."),
) -> None:
    """Lavora i video in coda (o uno specifico)."""
    st = _state(ctx)
    pipeline = _build_pipeline(st)
    if video:
        vid = extract_video_id(video) or video
        _print_outcome(pipeline.process_now(vid, force_from=from_stage))
        return
    n = pipeline.run_pending(max_items)
    console.print(f"Video lavorati: {n}")


@app.command()
def render(ctx: typer.Context, video: str = typer.Argument(..., help="ID o link del video.")) -> None:
    """Rigenera report.md e report.html dagli artefatti già salvati (nessuna chiamata a YouTube o all'AI)."""
    from ytkb.llm.schemas import AnalysisResult
    from ytkb.models import Transcript, VideoMeta
    from ytkb.pipeline import workspace as W
    from ytkb.pipeline.workspace import Workspace, find_existing
    from ytkb.report.channel_index import update_channel_index
    from ytkb.report.render import write_reports
    from ytkb.report.viewmodel import build_report_vm
    from ytkb.visual.models import VisualReport

    st = _state(ctx)
    vid = extract_video_id(video) or video
    row = st.db.get_video(vid)
    root = (row.archive_dir if row and row.archive_dir else None) or find_existing(st.settings.archive_dir, vid)
    if not root:
        console.print(f"[red]Nessun archivio per {vid}[/red]")
        raise typer.Exit(1)
    ws = Workspace(root)
    meta, transcript = ws.load(W.METADATA, VideoMeta), ws.load(W.TRANSCRIPT, Transcript)
    analysis = ws.load(W.ANALYSIS, AnalysisResult)
    if not (meta and transcript and analysis):
        console.print("[red]Mancano metadata.json, transcript.json o analysis.json: serve `ytkb process`.[/red]")
        raise typer.Exit(1)
    vm = build_report_vm(meta, transcript, analysis, ws.load(W.VISUAL, VisualReport), st.settings, ws.root)
    md, html = write_reports(vm, ws.root)
    update_channel_index(ws.channel_dir, st.settings.report.timezone)
    console.print(f"[green]Rigenerati:[/green]\n   {md}\n   {html}")


@app.command()
def costs(ctx: typer.Context, days: int = typer.Option(7, help="Quanti giorni mostrare.")) -> None:
    """Spesa stimata per le chiamate AI."""
    from datetime import timedelta

    from ytkb.utils.timeutil import utcnow

    st = _state(ctx)
    rows = st.db.llm_cost_summary(utcnow() - timedelta(days=days))
    if not rows:
        console.print("Nessuna chiamata AI registrata nel periodo.")
        return
    table = Table(title=f"Costi stimati (ultimi {days} giorni)")
    for col in ("Giorno", "Uso", "Modello", "Chiamate", "Token in", "Token out", "USD"):
        table.add_column(col)
    total = 0.0
    for r in rows:
        total += r["cost_usd"] or 0
        table.add_row(r["day"], r["purpose"], r["model"], str(r["calls"]), f"{r['input_tokens']:,}",
                      f"{r['output_tokens']:,}", f"{r['cost_usd']:.4f}")
    console.print(table)
    console.print(f"Totale: [bold]{total:.4f} $[/bold] (stima: verifica i prezzi in llm.pricing)")


def main() -> None:
    """Punto di ingresso: trasforma gli errori di configurazione in messaggi leggibili."""
    try:
        app()
    except ConfigError as exc:
        Console(stderr=True).print(f"[red]{exc}[/red]")
        sys.exit(2)
