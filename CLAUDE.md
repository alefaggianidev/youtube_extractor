# CLAUDE.md — yt-finance-kb (v2)

Istruzioni operative per Claude (e per chiunque sviluppi questo repository).
Il **perché** delle scelte è in `documentazione/` — in particolare `02-analisi-critica-v1.md` (cosa è cambiato rispetto al v1,
che resta nella history git) e `04-decisioni.md` (registro delle decisioni D-xxx). Questo file contiene le **regole**.

## 1. Obiettivo
Sistema personale (un solo utente) che, dato un video YouTube di finanza/trading/macro — passato a mano (CLI, Telegram) o
scoperto automaticamente tra i canali seguiti — produce un **report in italiano** che fa risparmiare tempo:
TL;DR, "vale la pena guardarlo?" con i minuti consigliati, setup operativi con livelli e **provenienza dei numeri**,
concetti didattici, macro, e **screenshot dei grafici** nei punti in cui chi parla vi fa riferimento.
Gira su una **VM RHEL 9**. Nome del pacchetto/CLI: `ytkb`.

## 2. Regole fondamentali (non negoziabili)
1. **Tutto dentro questa cartella.** Nessun file di progetto fuori dal repository (ambienti virtuali e cache esclusi).
2. **Ogni modifica significativa = commit git** con messaggio in italiano, formato `tipo(ambito): descrizione`
   (tipi: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `build`). Un commit per unità logica. **Mai `push`** senza
   richiesta esplicita.
3. **Documentazione sempre aggiornata.** Ogni passo rilevante aggiunge una voce a `documentazione/diario-di-sviluppo.md`
   (cosa, perché, esempio) e aggiorna `documentazione/roadmap.md`. Se cambia un comportamento, si aggiornano i documenti
   relativi. Stile: semplice, con esempi.
4. **Decisioni tracciate.** Una scelta architetturale nuova o cambiata = una scheda in `documentazione/04-decisioni.md`.
5. **Segreti mai in git.** Chiavi API, token Telegram, cookie e proxy stanno in `.env` / `config/*.yaml` locali (ignorati da
   git). Mai stamparli nei log.
6. **Test senza rete.** YouTube, Gemini e Telegram si simulano (fake, fixture, `httpx.MockTransport`). Ogni modulo nuovo ha
   i suoi test. `uv run pytest` deve essere verde prima di ogni commit di codice.
7. **Modelli LLM solo in configurazione**, mai nel codice.
8. **L'LLM non scrive timestamp:** cita ID di segmento; i secondi li calcola il codice (D-003).
9. **Ogni numero nel report ha una provenienza:** 🗣️ detto a voce (verificato), 👁️ letto dal grafico, 🤖 non verificato (D-005).
10. **Degrado elegante:** se uno stadio opzionale (locate, capture, read, clip, notifica) fallisce, il report esce comunque e
    dice cosa manca.
11. **Mai scaricare video interi.** Solo metadati, sottotitoli e sezioni di pochi secondi.
12. **Mai usare i cookie dell'account Google principale** dell'utente.

## 3. Architettura (sintesi — dettagli in `documentazione/03-architettura.md`)
Pipeline per video, 8 stadi con checkpoint su disco (artefatto valido ⇒ stadio saltato):

| # | Stadio | Artefatto | Opzionale |
|---|---|---|---|
| 1 | `metadata` — yt-dlp senza download; Short/live/premiere/disponibilità → decide skip/attesa | `metadata.json` | no |
| 2 | `transcript` — catena `transcript_api → ytdlp_subs → gemini_url` + segmenti numerati ~20 s | `transcript.json`, `transcript.txt` | no |
| 3 | `analysis` — LLM sul testo segmentato → `AnalysisResult` (Pydantic) + post-verifiche nel codice | `analysis.json` | no |
| 4 | `locate` — Gemini guarda le finestre dei `VisualTrigger` via link YouTube con offset | `visual.json` | sì |
| 5 | `capture` — una chiamata yt-dlp con più sezioni (solo video ≤1080p) + ffmpeg + frame più nitido | `frames/`, `clips/` | sì |
| 6 | `read` — vision sul frame ad alta risoluzione con `vision_question` | `visual.json` | sì |
| 7 | `render` — view-model → `report.md` (Obsidian) + `report.html` (autocontenuto) | `report.*` | no |
| 8 | `publish` — `channel_index.md`, knowledge base, notifica Telegram | — | notifica sì |

Stati del video in SQLite: `queued`, `waiting`, `processing`, `done`, `skipped`, `failed` (backoff configurabile).
Ingressi: RSS (primario) + YouTube Data API con API key (fallback), CLI, bot Telegram (whitelist `chat_id`).

## 4. Stack
- **Python 3.12**, dipendenze con **uv** (`pyproject.toml` + `uv.lock`).
- `google-genai` (Interactions API), `pydantic` v2 + `pydantic-settings`, `PyYAML`, `Jinja2`, `httpx`, `typer`.
- `yt-dlp[default]` (include `yt-dlp-ejs`) + **`deno` da PyPI** (D-013); opzionale `bgutil-ytdlp-pot-provider`.
- `youtube-transcript-api`, `feedparser`, `Pillow` + `numpy` (niente OpenCV, D-011), `ffmpeg` di sistema.
- Database: SQLite (stdlib). Niente Redis/Celery/Postgres (D-007).
- Produzione: **Podman + Quadlet** su RHEL 9, volumi con `:Z` (D-012).

## 5. Struttura del repository
```text
CLAUDE.md              # questo file
README.md              # presentazione e avvio rapido
pyproject.toml         # progetto e dipendenze (uv)
config/                # *.example.yaml versionati; settings.yaml e channels.yaml locali (ignorati)
.env.example           # elenco dei segreti; .env locale (ignorato)
src/ytkb/              # codice (vedi documentazione/03-architettura.md §4)
tests/                 # pytest; fixture in tests/fixtures/
deploy/                # Containerfile, Quadlet, script RHEL 9
documentazione/        # spiegazioni semplici, decisioni, roadmap, diario
data/                  # stato, archivio, file temporanei (ignorata da git)
```

## 6. Comandi
```bash
uv sync                          # installa/aggiorna l'ambiente
uv run pytest -q                 # test (obbligatori prima di ogni commit di codice)
uv run ruff check src tests      # lint
uv run ytkb init                 # crea config/ e data/ dai file di esempio
uv run ytkb doctor               # diagnosi: Deno, ffmpeg, yt-dlp, rete, chiavi
uv run ytkb add <URL> --now      # processa subito un video
uv run ytkb status               # stato della coda
uv run ytkb run                  # demone: polling + worker + bot
```
Nell'ambiente di sviluppo di Claude (Linux sulla macchina dell'utente, cartella montata da Windows) l'ambiente virtuale va
tenuto **fuori** dalla cartella: `export UV_PROJECT_ENVIRONMENT=$HOME/venvs/ytkb` prima di `uv sync`/`uv run`.

## 7. Convenzioni di codice
- Type hints ovunque; modelli Pydantic per i dati che attraversano i confini (YouTube, LLM, disco).
- **Identificatori in inglese**; docstring, commenti, prompt, messaggi utente e report **in italiano** (D-016).
- I/O esterno solo negli adapter (`youtube/`, `llm/`, `notify/`), iniettati tramite il contesto della pipeline → testabili.
- Errori tipizzati in `ytkb/errors.py`: `NotReadyError`, `TemporaryError`, `BlockedError`, `PermanentError`, `SkipError`.
- Scritture su disco atomiche (file temporaneo + rinomina). Nomi di file/cartelle compatibili Windows.
- Logging con il modulo `logging` (niente `print` fuori dalla CLI); mai segreti nei log.
- Prompt in `src/ytkb/llm/prompts/*.md`, non dentro il codice.
- Dipendenze nuove pesanti solo con una scheda in `04-decisioni.md`.

## 8. Vincoli RHEL 9
- SELinux *enforcing*: volumi del container con `:Z`.
- Python 3.12 (AppStream) o container `python:3.12-slim` con ffmpeg.
- yt-dlp va aggiornato spesso (YouTube cambia): aggiornamento all'avvio del container + ricostruzione periodica.
- Nessuna porta in ingresso necessaria (Telegram in long polling).
- Se la VM è in cloud, YouTube può bloccare l'IP: prevedere `ytdlp.proxy` e il provider PO token opzionale.

## 9. Stato dei lavori
Fase corrente e checklist in `documentazione/roadmap.md`. Aggiornare quella tabella, non questo file.
