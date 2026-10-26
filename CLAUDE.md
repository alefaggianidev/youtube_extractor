# RUOLO E OBIETTIVO
Sei un Senior Software Architect e Python Engineer. Devi progettare e scrivere da zero un sistema completo, modulare e pronto per la produzione chiamato `yt-finance-kb`.
Lo scopo del sistema è analizzare video YouTube di finanza, trading, investimenti e macroeconomia (sia inseriti manualmente tramite link/Bot Telegram, sia intercettati automaticamente tramite i feed RSS dei canali seguiti), estrarre in modo chirurgico screenshot di grafici/slide e micro-clip video quando chi parla vi fa riferimento, e generare un report strutturato salvato su filesystem organizzato per Canale e per Video.

---

# 1. AMBIENTE DI ESECUZIONE E VINCOLI INFRASTRUTTURALI (RHEL 9)
- **Sistema Operativo Host:** Red Hat Enterprise Linux 9 (RHEL 9).
- **Containerizzazione:** Podman + `podman-compose` (compatibile con Quadlets/systemd).
- **Attenzione a SELinux:** Su RHEL 9 SELinux è in modalità `Enforcing`. Tutti i bind mount nel file `compose.yaml` (in particolare la directory di output `./archive` e `./config`) DEVONO utilizzare il suffisso `:Z` (es. `./archive:/app/archive:Z`).
- **Linguaggio e Stack:** Python 3.11+, gestione dipendenze con `uv` o `pip`, `pydantic` v2 per la validazione rigorosa degli output LLM, `google-genai` (SDK ufficiale per Gemini 2.5 Flash/Pro), `yt-dlp` (con runtime `deno` o `nodejs` nel container per risolvere le challenge JS di YouTube), `ffmpeg`, `opencv-python-headless`, `youtube-transcript-api`, `feedparser`, `aiogram` (per il bot Telegram).

---

# 2. ARCHITETTURA DELLA PIPELINE ("TRANSCRIPT-FIRST & SURGICAL MEDIA")
NON scaricare mai l'intero video YouTube a priori. Implementa rigorosamente questa pipeline a 5 stadi:

### Stadio 1: Ingestion Ibrida (Automatica + Manuale)
1. **Monitoraggio Canali (RSS Poller):** Legge un file `config/channels.yaml` contenente la lista dei canali YouTube (`channel_id` e `channel_name`). Interroga periodicamente il feed pubblico `https://www.youtube.com/feeds/videos.xml?channel_id={ID}` senza usare quote API OAuth. Tiene traccia dei video già processati in un database leggero SQLite (`state/processed_videos.db`).
2. **Input Manuale (CLI + Telegram Bot + API):** Permette di passare un URL YouTube manualmente tramite comando CLI, messaggio a un Bot Telegram privato o endpoint locale.

### Stadio 2: Estrazione Veloce del Transcript
1. Tenta il recupero immediato dei sottotitoli (manuali o auto-generati, IT o EN) tramite `youtube-transcript-api` mantenendo i timestamp esatti (`start`, `duration`, `text`).
2. **Fallback Audio:** Se il video non ha sottotitoli, scarica SOLO la traccia audio leggera (`yt-dlp -f "ba"`) e trascrivila con i timestamp usando il modello Gemini o un'API Whisper compatibile.
3. Formatta il transcript con marcatori temporali leggibili `[MM:SS]` ogni frase/blocco.

### Stadio 3: Analisi Semantica Dual-Mode e "Visual Trigger Detection" (LLM Pass 1)
Invia il transcript completo all'LLM chiedendo un output JSON strutturato (tramite Pydantic `response_schema`).
Poiché i video di finanza/trading contengono sia analisi operativa che formazione/teoria, lo schema DEVE estrarre:
1. **Classificazione del Video:** `OPERATIONAL_TRADING`, `EDUCATIONAL_THEORY`, `MACRO_ANALYSIS`, oppure `HYBRID`.
2. **Sintesi Esecutiva (TL;DR):** Riassunto denso dei punti chiave.
3. **Sezione Operativa (se presente):** Lista degli asset/ticker analizzati, timeframe, bias (Bullish/Bearish/Neutral), tesi operativa, livelli menzionati a voce.
4. **Sezione Didattica / Teorica / Approfondimento (se presente):**
   - Concetti teorici spiegati (es. struttura di mercato, cicli, indicatori, psicologia, gestione del rischio, concetti macroeconomici).
   - Regole passo-passo o metodologie spiegate nel video.
   - Esempi pratici, formule o configurazioni di tool/indicatori citati.
5. **Lista dei `VisualTrigger`:** Ogni volta che il relatore fa riferimento a qualcosa sullo schermo (es. *"guardate questo grafico"*, *"questo livello qui"*, *"come vedete in questa slide"*, *"ecco i risultati del backtest"*, *"impostate l'indicatore così"*), l'LLM deve generare un oggetto `VisualTrigger` con:
   - `timestamp_start` (MM:SS) e `timestamp_end` (MM:SS)
   - `trigger_type`: `PRICE_CHART` | `EDUCATIONAL_SLIDE` | `INDICATOR_SETTINGS` | `DATA_TABLE` | `OTHER`
   - `needs_video_clip`: booleano (`True` se l'azione dinamica col cursore/replay di mercato è essenziale, `False` se basta uno screenshot statico ad alta risoluzione)
   - `spoken_context`: cosa dice l'autore in quel momento
   - `vision_question`: la domanda specifica da porre al modello Vision nello stadio 5 (es. *"Quali sono i prezzi esatti delle linee di supporto e resistenza mostrate sul grafico?"* oppure *"Trascrivi le regole e lo schema presenti in questa slide didattica"*).

### Stadio 4: Estrazione Chirurgica di Immagini e Micro-Clip
Per ogni `VisualTrigger` (limita a un massimo configurabile, es. 8 per video, ordinati per importanza):
1. Usa `yt-dlp --download-sections "*{start-2s}-{end+3s}"` per scaricare SOLO quel segmento video in 1080p.
2. **Smart Frame Picker:** Dal segmento scaricato, estrai 1 frame ogni 1.5 secondi con `ffmpeg`. Usa OpenCV per scartare frame sfocati (Laplacian variance) o dove predomina la webcam a tutto schermo, selezionando il frame con maggiore nitidezza e densità informativa (grafici/testo). Salva il frame migliore in `frames/`.
3. Se `needs_video_clip == True`, ritaglia e comprimi il segmento video (`H.264`, audio AAC) salvandolo in `clips/`.

### Stadio 5: Lettura Visiva (LLM Vision Pass 2) e Generazione Report
1. Per ogni frame estratto nello Stadio 4, invia l'immagine all'LLM Multimodale insieme a `spoken_context` e `vision_question`.
2. Ottieni la risposta precisa (es. i livelli numerici letti sull'asse Y di TradingView che l'autore aveva chiamato semplicemente *"qui"*, oppure la spiegazione dettagliata dello schema teorico mostrato nella slide).
3. Compila il report finale in Markdown (`report.md`) unendo l'analisi testuale, i moduli didattici, i setup operativi e incorporando nel punto giusto gli screenshot (`![Descrizione](./frames/...)`) con l'analisi visiva e i link alle micro-clip (`[Guarda Clip Video](./clips/...)`).

---

# 3. STRUTTURA DELLE CARTELLE DI OUTPUT (PER CANALE E PER VIDEO)
Il sistema deve mantenere un archivio locale estremamente ordinato, compatibile con Obsidian o qualsiasi visualizzatore Markdown:

```text
archive/
├── Nome_Canale_Sanitizzato/
│   ├── channel_index.md                           # Indice aggiornato automaticamente con tutti i video del canale
│   └── 2026-10-26_Titolo_Del_Video_Sanitizzato_[VIDEO_ID]/
│       ├── report.md                              # Il report completo formattato (Operatività + Teoria + Grafici)
│       ├── metadata.json                          # Output JSON completo validato da Pydantic
│       ├── transcript.txt                         # Trascrizione completa con timestamp [MM:SS]
│       ├── frames/
│       │   ├── 03m15s_chart_BTCUSDT.png
│       │   └── 14m20s_slide_teoria_wyckoff.png
│       └── clips/
│           └── 08m10s-08m28s_esempio_ingresso.mp4