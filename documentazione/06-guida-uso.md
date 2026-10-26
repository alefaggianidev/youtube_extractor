# 06 — Guida all'uso

Come si usa `ytkb`, con esempi. Questa guida cresce con le fasi: ora copre l'uso **manuale** (fase 1).
Per vedere com'è fatto un report senza installare nulla, apri l'[esempio](esempio-report/report.md)
(versione per il telefono: [report.html](esempio-report/report.html)).

## 1. Preparazione (una volta sola)

```bash
cd youtube_extractor
uv sync                 # installa Python, yt-dlp, Deno e tutte le dipendenze
uv run ytkb init        # crea config/settings.yaml, config/channels.yaml, .env e la cartella data/
```

Poi apri il file `.env` e incolla la chiave di Gemini:

```bash
GEMINI_API_KEY=la-tua-chiave      # https://aistudio.google.com/apikey
```

Controlla che sia tutto a posto:

```bash
uv run ytkb doctor
```

Esempio di risultato (abbreviato):

```text
 Controllo                  Esito  Dettaglio
 Python                     OK     3.12.15
 ffmpeg                     OK     ffmpeg version 6.1 ...
 Deno (per yt-dlp)          OK     deno 2.9.8
 yt-dlp                     OK     2026.10.26 (ejs 0.8.0)
 GEMINI_API_KEY             OK     presente
 Rete → feed RSS YouTube    OK     HTTP 200
 Rete → Gemini API          OK     HTTP 404     ← normale: basta che il server risponda
```

> 💡 **Prova senza chiave:** in `config/settings.yaml` imposta `llm: {provider: fake}`. Il sistema scarica comunque la
> trascrizione vera, ma il riassunto è finto e il report è marcato *"Report dimostrativo"*. Utile per verificare che
> YouTube sia raggiungibile dalla tua VM senza spendere nulla.

## 2. Analizzare un video adesso

```bash
uv run ytkb add --now https://youtu.be/ID_DEL_VIDEO
```

Cosa vedi:

```text
In coda: ID_DEL_VIDEO
⚙️  Elaboro ID_DEL_VIDEO…
✅ fatto BTC e S&P500: settimana decisiva
   📄 data/archive/Trading_Facile/2026-10-26_BTC_e_S_P500_settimana_decisiva_[ID_DEL_VIDEO]/report.md
   🌐 data/archive/Trading_Facile/2026-10-26_BTC_e_S_P500_settimana_decisiva_[ID_DEL_VIDEO]/report.html
```

Il link può essere in qualunque forma: `youtu.be/…`, `youtube.com/watch?v=…`, `…/shorts/…`, `…/live/…`, o solo l'ID.
Puoi passarne più di uno nello stesso comando.

Senza `--now` il video viene solo **messo in coda** (con priorità alta): lo lavorerà il demone (fase 3) oppure:

```bash
uv run ytkb process            # lavora tutti i video in coda e in scadenza
```

## 3. Controllare cosa succede

```bash
uv run ytkb status             # riepilogo e ultimi video
uv run ytkb status --status failed
uv run ytkb show ID_DEL_VIDEO  # dettagli ed eventi di un video
```

| Stato | Cosa significa | Cosa fare |
|---|---|---|
| 🕒 in coda | Da lavorare | niente |
| ⏳ in attesa | YouTube non è pronto (premiere, live, sottotitoli) o budget del giorno esaurito | niente: riprova da solo |
| ✅ fatto | Report pronto | leggilo 🙂 |
| ⏭️ saltato | Short, troppo lungo/corto, solo membri | se lo vuoi comunque: `ytkb add --now --force URL` |
| ❌ fallito | Errore permanente o troppi tentativi | `ytkb show ID` per il motivo, poi `ytkb retry ID` |

## 4. Rifare solo una parte

Ogni stadio salva il suo risultato (checkpoint). Puoi rifare la pipeline da un certo punto in poi:

```bash
uv run ytkb process ID_DEL_VIDEO --from analysis   # rifà analisi e report (es. dopo aver cambiato modello)
uv run ytkb process ID_DEL_VIDEO --from transcript # riscarica anche la trascrizione
uv run ytkb render ID_DEL_VIDEO                    # rigenera solo il report: zero chiamate a YouTube o all'AI
```

## 5. Quanto sto spendendo?

```bash
uv run ytkb costs --days 7
```

Mostra, giorno per giorno, chiamate, token e costo **stimato** con i prezzi di `llm.pricing` in `config/settings.yaml`.

## 6. Dove sono i report

```text
data/archive/
└── <Canale>/
    ├── channel_index.md                     # indice di tutti i video del canale
    └── <data>_<titolo>_[<ID>]/
        ├── report.md                        # per Obsidian (o qualsiasi editor Markdown)
        ├── report.html                      # autocontenuto: si apre ovunque, anche dal telefono
        ├── transcript.txt                   # trascrizione leggibile [MM:SS] testo
        └── ...                              # file tecnici (json) usati come checkpoint
```

**Obsidian:** apri la cartella `data/archive` come *vault*. Le intestazioni dei report contengono asset, bias, tipo e
punteggio: con il plugin Dataview puoi fare tabelle tipo "tutti i video rialzisti su BTC".

## 7. Grafici e screenshot (riferimenti visivi)

Per ogni momento in cui chi parla mostra qualcosa ("guardate questo grafico…"), il sistema:

1. **localizza** — chiede a Gemini di guardare solo quella finestra del video (es. 13:09–13:30) e di indicare il
   secondo in cui lo schermo è più chiaro (*solo video pubblici*);
2. **cattura** — scarica **3 secondi** attorno a quel secondo e tiene il fotogramma più nitido;
3. **legge** — chiede a Gemini di leggere lo screenshot in alta risoluzione (livelli, testo delle slide…).

Si regola in `config/settings.yaml`, sezione `visual`:

| Chiave | Default | A cosa serve |
|---|---|---|
| `enabled` | `true` | Spegne tutta la parte visiva |
| `max_triggers` | `8` | Massimo momenti per video (i più importanti) |
| `locate` / `capture` / `read_frame` | `true` | Accendi/spegni i singoli passaggi |
| `capture_height` | `1080` | Risoluzione degli screenshot |
| `clips` | `false` | Micro-clip MP4 per i momenti "in movimento" (replay, disegno dal vivo) |

Se un passaggio fallisce (es. YouTube blocca il download), il report esce comunque: al posto dell'immagine trovi la
descrizione di cosa c'era a schermo e il link al secondo esatto, e una nota spiega cosa è mancato. Per riprovare solo la
parte visiva:

```bash
uv run ytkb process ID_DEL_VIDEO --from locate
```
