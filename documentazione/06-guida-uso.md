# 06 — Guida all'uso

Come si usa `ytkb`, con esempi: uso manuale (sezioni 1-7), automatico sui canali che segui (sezione 8) e
Telegram sul telefono (sezione 9).
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

## 8. In automatico: i canali che segui

### Importare le tue iscrizioni (consigliato)
1. Vai su <https://takeout.google.com>, deseleziona tutto, seleziona **YouTube e YouTube Music** →
   "Tutti i dati di YouTube inclusi" → lascia solo **iscrizioni** → esporta.
2. Nel file scaricato trovi `subscriptions.csv`. Importalo:

```bash
uv run ytkb channels import-takeout ~/Downloads/subscriptions.csv
# Trovati 37 canali, aggiunti 37 in config/channels.yaml
```

   Se segui molti canali non di finanza, importali disattivati e attiva solo quelli giusti:
   `uv run ytkb channels import-takeout --disabled subscriptions.csv` e poi
   `uv run ytkb channels enable "Nome canale"`.
3. Disattiva quelli che non c'entrano con la finanza:

```bash
uv run ytkb channels list
uv run ytkb channels disable "Canale di cucina"     # per nome o per ID
```

Puoi anche aggiungerli uno alla volta: `uv run ytkb channels add @NomeCanale` (oppure il link del canale).
Il file `config/channels.yaml` si può modificare anche a mano, per esempio per dare a un canale filtri suoi:

```yaml
channels:
  - id: UCxxxxxxxxxxxxxxxxxxxxxx
    name: Trading Facile
    enabled: true
    filters:
      max_duration_s: 7200   # per questo canale accetto video fino a 2 ore
```

### Avviare il demone

```bash
uv run ytkb run
```

Ogni 15 minuti controlla i feed dei canali e mette in coda i video nuovi (ignorando gli Shorts e, al primo avvio, i
video più vecchi di 48 ore); intanto lavora la coda un video alla volta. Si ferma con Ctrl+C. Sulla VM girerà come
servizio (fase 5). `ytkb status` mostra se il demone è attivo.

Un controllo singolo, senza demone: `uv run ytkb poll` (poi `uv run ytkb process`).

### Cosa succede a un video appena caricato (esempio)

| Ora | Evento | Stato |
|---|---|---|
| 18:02 | Il canale pubblica il video | — |
| 18:15 | Il controllo dei feed lo trova | 🕒 in coda |
| 18:15 | Sottotitoli non ancora pronti | ⏳ in attesa (riprova alle 18:35) |
| 18:35 | Sottotitoli pronti → trascrizione, analisi, grafici | ⚙️ in lavorazione |
| 18:38 | Report pronto (e notifica, con Telegram) | ✅ fatto |

Una **premiere** delle 21:00 resta *in attesa* fino alle 21:10; una **diretta** viene analizzata quando finisce.
Se dopo 4 ore i sottotitoli automatici non sono ancora arrivati, la trascrizione la fa Gemini dal link del video.

### Il trucco della playlist "da riassumere" (dal telefono, senza bot)
1. Su YouTube crea una playlist **non in elenco** (o pubblica) chiamata, per esempio, "Da riassumere".
2. Copia il suo ID (la parte dopo `list=` nel link, inizia con `PL`) in `config/settings.yaml`:

```yaml
monitor:
  watch_playlists: [PLxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx]
```

3. Dal telefono, su qualsiasi video: **Salva → Da riassumere**. Al controllo successivo il video viene analizzato,
   senza filtri di durata e con priorità alta.

> Nota: la playlist "Guarda più tardi" non funziona, perché YouTube non la rende leggibile ai programmi.

### Se il feed RSS non risponde
YouTube a volte risponde "404" sui feed per qualche ora. Se hai messo `YOUTUBE_API_KEY` nel file `.env`, il sistema
usa automaticamente la YouTube Data API come piano B (costa 1 unità di quota per canale; ne hai 10.000 gratis al
giorno). Per crearla: Google Cloud Console → nuovo progetto → abilita "YouTube Data API v3" → Credenziali →
"Crea credenziali" → **Chiave API** (non serve OAuth).

## 9. Telegram: i report sul telefono

Quando un video è pronto ricevi un messaggio con il riassunto (TL;DR, voto, minuti da guardare, asset e livelli) e,
in allegato, il **report HTML completo** con i grafici. Puoi anche **mandare un link** al bot per farlo analizzare.

### Configurazione (5 minuti, una volta sola)
1. Su Telegram apri **@BotFather** → `/newbot` → scegli nome e username → copia il **token**.
2. Mettilo nel file `.env`: `TELEGRAM_BOT_TOKEN=123456:ABC...`
3. Dal telefono scrivi `/start` al tuo bot, poi sul PC/VM:

```bash
uv run ytkb telegram chat-id
# chat_id 123456789  Alessandro
```

4. In `config/settings.yaml`:

```yaml
telegram:
  enabled: true
  allowed_chat_ids: [123456789]
```

5. Prova: `uv run ytkb telegram test` → ti arriva "il collegamento con Telegram funziona".
6. Riavvia il demone (`uv run ytkb run`): da ora il bot risponde.

### Cosa puoi scrivere al bot

| Messaggio | Risposta |
|---|---|
| un link YouTube (anche più di uno, anche dentro un testo) | ✅ In coda… e poi il report quando è pronto |
| un link già analizzato | ♻️ ti rimanda il report |
| `/stato` | quanti video in coda, in attesa, fatti… e gli ultimi 5 |
| `/start` o `/aiuto` | istruzioni e il tuo chat_id |

**Sicurezza:** il bot risponde solo alle chat in `allowed_chat_ids`; a chiunque altro risponde "chat non
autorizzata" senza fare nulla. Il token non viene mai scritto nei log. La VM non deve aprire porte: è lei a
chiamare Telegram (*long polling*).
