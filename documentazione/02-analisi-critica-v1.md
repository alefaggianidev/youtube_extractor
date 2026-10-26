# 02 — Analisi critica del progetto originale (CLAUDE.md v1)

> **In breve.** L'idea di fondo del v1 — *prima il testo, poi solo i pezzetti di video che servono* — è giusta e la teniamo.
> Però il v1 aveva quattro punti deboli che in produzione lo avrebbero fatto fallire o costare troppo:
> 1. indica **modelli Gemini già superati** e un'API che Google ora chiama "legacy";
> 2. sceglie i momenti con i grafici **senza guardare lo schermo** e facendo scrivere i timestamp all'AI (che sbaglia);
> 3. ignora il **rischio n.1** di questi sistemi: YouTube che blocca i download fatti da server;
> 4. non gestisce **i tempi reali di un video appena caricato** (sottotitoli non ancora pronti, premiere, live, Shorts).
>
> A questi si aggiungono lacune su costi, sicurezza del bot, affidabilità dei feed e — soprattutto — manca il vero
> moltiplicatore di tempo risparmiato: **l'aggregazione** di più video in un unico digest.

Il testo originale è salvato nella history git (commit `chore: baseline con il CLAUDE.md originale (v1)`).
Tutte le verifiche sono state fatte il **27 ottobre 2026**: le fonti sono in fondo.

---

## 1. Cosa teniamo (perché è giusto)

| Scelta del v1 | Perché è giusta | Esempio |
|---|---|---|
| **Transcript-first** | Il parlato contiene la maggior parte delle informazioni ed è testo: costa pochissimo. | 1 ora di video come testo ≈ 15.000 token; come video ≈ 360.000–1.000.000 token. |
| **RSS senza OAuth** | Zero quote, zero login, zero rischi per il tuo account. | `https://www.youtube.com/feeds/videos.xml?channel_id=UC...` |
| **Download chirurgico** (`--download-sections`) | Si scaricano pochi secondi invece di un file da 1 GB: meno banda, meno richieste "sospette". | 8 screenshot = ~30 secondi di video totali. |
| **Output JSON validato con Pydantic** | Il report si costruisce da dati strutturati, non da testo libero. Se il JSON è sbagliato ce ne accorgiamo subito. | |
| **Doppia modalità operativa/didattica** | Ottima intuizione di dominio: un video di "analisi BTC" e una "lezione su Wyckoff" vanno riassunti in modo diverso. | |
| **`VisualTrigger` con `vision_question`** | Il primo passaggio dice al secondo *cosa cercare* nell'immagine. Idea furba, la teniamo. | *"Quali livelli orizzontali sono disegnati e a che prezzo?"* |
| **SELinux `:Z`, Deno per yt-dlp** | Corretto e aggiornato. | |
| **Archivio per canale/video compatibile Obsidian** | Ha valore nel tempo: diventa la tua biblioteca personale. | |

---

## 2. Problemi trovati (in ordine di gravità) e correzioni

### P1 — I modelli indicati sono già superati
**Cosa dice il v1:** "Gemini 2.5 Flash/Pro" con l'SDK `google-genai`.

**Situazione reale (ottobre 2026):**
- La pagina ufficiale delle deprecazioni dice che l'accesso ai modelli 2.5 è **limitato a chi li ha usati di recente** e raccomanda per i nuovi progetti **Gemini 3.8 Flash** o **3.5 Flash-Lite**. Un progetto nuovo rischia di non poter usare 2.5 del tutto.
- L'API classica `generateContent` è etichettata **"Legacy"**: resta supportata, ma Google raccomanda la nuova **Interactions API** per i nuovi sviluppi.
- Prezzi di `gemini-3.8-flash`: **0,75 $ per milione di token in input e 3,75 $ in output**; il listino indica che **raddoppiano dal 1° gennaio 2027**. Esiste il livello di servizio **"flex"** con prezzo dimezzato (risposta più lenta: per un report non urgente è perfetto).

**Correzione:**
- I nomi dei modelli stanno **solo nella configurazione**, mai nel codice (quando Google cambia modello si modifica una riga).
- Default: `gemini-3.8-flash` via Interactions API, `service_tier: flex`.
- Ogni chiamata registra i token consumati e il costo stimato (vedi [05 — Costi](05-costi.md)).

### P2 — I momenti "visivi" vengono scelti a occhi chiusi
**Cosa fa il v1:** lo Stadio 3 legge **solo la trascrizione** e decide dove ci sono grafici importanti, scrivendo timestamp `MM:SS`.

**Perché non funziona bene:**
- In un tipico video di trading (schermo TradingView condiviso) il grafico è visibile **per tutto il video** e chi parla dice "qui", "questo livello" decine di volte. Dal solo testo è impossibile sapere *cosa* c'è sullo schermo e *quali* momenti contano davvero.
- Gli LLM sono imprecisi nel riscrivere timestamp di un testo lungo: arrotondano o li inventano. Un errore di 20 secondi = screenshot del grafico sbagliato.

**Esempio:** il testo *"…e quindi guardate qui, questo livello è fondamentale…"* non dice né l'asset, né il livello, né il timeframe.

**Correzione (due mosse):**
1. **Segmenti numerati.** La trascrizione viene inviata così: `[S042 13:12] come vedete qui il prezzo è tornato sul supporto…`. L'LLM risponde *"segmento 42"*; il **codice** converte in secondi esatti. L'LLM non scrive mai un timestamp.
2. **Nuovo stadio "Localizza".** Prima di scaricare qualsiasi cosa, chiediamo a Gemini di **guardare davvero** la finestra di video (es. 13:09–13:30) passando direttamente il **link YouTube** con inizio/fine. È Google a leggere il video: noi non scarichiamo niente. Gemini ci dice cosa c'è sullo schermo, se vale la pena catturarlo e **il secondo esatto migliore**. Secondo la documentazione questa funzione è in *preview* e attualmente gratuita (solo video pubblici).

### P3 — Numeri letti dai grafici: rischio di numeri inventati
**Cosa fa il v1:** chiede al modello vision i "prezzi esatti delle linee sull'asse Y".

**Perché è pericoloso:** in finanza un numero sbagliato è peggio di nessun numero. I modelli vision leggono bene le etichette grandi ma possono sbagliare o inventare valori piccoli sull'asse.

**Correzione — provenienza obbligatoria di ogni numero:**

| Simbolo | Significato | Come lo verifichiamo |
|---|---|---|
| 🗣️ | **detto a voce** | Il codice controlla che le parole esatte compaiano nella trascrizione in quel segmento |
| 👁️ | **letto dal grafico** | Viene dalla lettura dell'immagine: *da verificare a occhio* (lo screenshot è lì accanto) |
| 🤖 | **dedotto/non verificato** | L'AI lo riporta ma non lo troviamo nel testo: lo segnaliamo come tale |

Esempio nel report: `Supporto 60.000 🗣️ [13:12]` · `Resistenza 64.480 👁️ letto dal grafico`.

### P4 — Il rischio n.1 non è citato: YouTube blocca i server
**Fatti verificati:**
- **youtube-transcript-api**: il README avverte che YouTube **blocca la maggior parte degli IP dei cloud provider** (errori `RequestBlocked`/`IpBlocked`), consiglia proxy residenziali a rotazione, dice che **l'autenticazione via cookie è attualmente rotta** e che la libreria usa un'API non documentata che può smettere di funzionare senza preavviso.
- **yt-dlp**: dalla versione 2025.11.12 serve un **runtime JavaScript** (Deno è l'unico abilitato di default) più il componente `yt-dlp-ejs`; YouTube richiede un **PO token** ("prova di origine") per la maggior parte delle richieste dei formati video su alcuni client (si risolve con il plugin `bgutil-ytdlp-pot-provider`); da IP di datacenter compare spesso *"Sign in to confirm you're not a bot"*.
- yt-dlp esce con versioni nuove molto spesso (l'ultima è del 26/10/2026): **se non lo aggiorni, prima o poi smette di funzionare.**

**La domanda chiave è: dove gira la VM RHEL 9?**
- **Casa/ufficio** (IP residenziale o aziendale): di solito funziona.
- **Cloud** (AWS, Azure, GCP, Hetzner, OVH…): quasi certamente bloccata senza proxy residenziale.

**Correzione:**
1. **Catena di fallback per la trascrizione:** `youtube-transcript-api` → sottotitoli via `yt-dlp` → **Gemini direttamente sul link YouTube** (è Google a prendere il video, quindi il blocco del nostro IP non conta) → *(ultima spiaggia)* download dell'audio e trascrizione.
2. **Degrado elegante:** se il download dei frame fallisce, il report esce comunque con la descrizione del grafico e il link al secondo esatto del video.
3. **`ytkb doctor`**: un comando che diagnostica tutto (Deno presente? yt-dlp aggiornato? YouTube raggiungibile? chiave Gemini valida?).
4. **Aggiornamento automatico** di yt-dlp.
5. **Mai i cookie del tuo account Google principale** (rischio di blocco dell'account). Se un giorno servissero: un account secondario.

### P5 — Il tempo reale di un video nuovo non è gestito
**Cosa succede davvero quando il feed segnala un video:**
- i **sottotitoli automatici** possono non essere pronti per minuti o ore (soprattutto sui video lunghi);
- **premiere e live programmate** compaiono nel feed *prima* di andare in onda;
- una **live in corso** non ha ancora una trascrizione completa;
- gli **Shorts** compaiono nel feed come video normali (e i canali finanza ne pubblicano tanti).

Il v1 tiene solo l'elenco dei "video già processati": un video arrivato troppo presto o fallisce per sempre o viene riprovato all'infinito.

**Correzione:** una **macchina a stati** (`in coda → in attesa → in lavorazione → fatto / saltato / fallito`) con tentativi e attese crescenti (*backoff*), più **checkpoint per stadio** salvati su disco: se fallisce la cattura dei frame, non si ripaga l'analisi LLM già fatta.

### P6 — L'RSS di YouTube non è affidabile al 100%
- Dal dicembre 2025 sono documentati periodi **di ore** in cui il feed risponde 404, poi torna da solo.
- Il feed mostra **solo gli ultimi 15 video** del canale.

**Correzione:** fallback automatico su **YouTube Data API v3** con una semplice *API key* (niente OAuth, niente accesso al tuo account): leggere la playlist "uploads" di un canale costa **1 unità**, la quota gratuita è **10.000 unità al giorno** → 50 canali controllati ogni 15 minuti = 4.800 unità/giorno.

E per le iscrizioni: il v1 ti chiede di scrivere a mano i `channel_id` in un YAML. **Correzione:** import automatico dal file `subscriptions.csv` di **Google Takeout**, oppure `ytkb channels add @nomecanale`.

### P7 — Manca il vero risparmio di tempo: l'aggregazione
10 video al giorno = 10 report da leggere. Meglio di 10 video, ma non abbastanza.

**Correzione:**
- **"Vale la pena guardarlo?"** — punteggio 1–5 con i minuti esatti da guardare.
- **Digest giornaliero** — un solo messaggio con i video del giorno raggruppati per asset (*"BTC: 3 canali rialzisti, 1 ribassista; 60.000 citato da 3 canali"*).
- **Knowledge base** — il progetto si chiama *yt-finance-kb* ma il v1 non ha una "kb": ricerca su tutte le trascrizioni + tabella delle menzioni (asset, bias, livelli, video, minuto). Esempio: *"cosa hanno detto su NVDA questa settimana?"*.

### P8 — Il bot Telegram "privato" non è definito
Un bot Telegram è raggiungibile da chiunque ne conosca il nome. Senza controllo, uno sconosciuto potrebbe fargli processare video **a tue spese**.

**Correzione:** whitelist dei `chat_id` autorizzati; segreti in `.env` con permessi `600`, mai in git, mai nei log.

### P9 — Alcune parti sono sovra-ingegnerizzate
| v1 | Problema | v2 |
|---|---|---|
| `podman-compose` | Strumento della community (EPEL), non il modo nativo di RHEL | **Quadlet** (Podman + systemd): riavvio automatico, log in journald. Compose solo opzionale per sviluppo |
| 4 ingressi dal giorno 1 (CLI, bot, API, RSS) | Più superficie, più bug | CLI + RSS + Telegram. Una pagina web solo se servirà |
| Micro-clip MP4 sempre | Spazio e tempo | Default: link `youtu.be/ID?t=490` al secondo esatto. Clip opzionali (utili se il video viene cancellato) |
| OpenCV + rilevamento webcam | Dipendenza pesante, euristica fragile | Il secondo giusto lo sceglie **Localizza**; per il frame più nitido bastano **Pillow + numpy** |
| `aiogram` (framework asincrono) | Troppo per un bot con un utente | 3 chiamate HTTP alla Bot API con `httpx` |

### P10 — Nessun controllo dei costi
Una live di 3 ore con 8 clip 1080p e più passaggi LLM non ha un tetto.

**Correzione:** filtri per canale (durata min/max, Shorts, live), massimo *N* riferimenti visivi per video, **budget giornaliero in dollari**, registro dei token consumati per chiamata.

### P11 — Dettagli mancanti
- **Lingua:** video in italiano o inglese → report sempre in italiano.
- **Sponsor:** molti canali di trading sono sponsorizzati da broker → conflitto di interessi da segnalare nel report.
- **Nomi file compatibili Windows** (l'archivio può essere aperto da Windows/Obsidian): niente `: ? * < > |`.
- **Fuso orario** Europe/Rome.
- **Test automatici senza rete:** nessun test deve chiamare YouTube, Gemini o Telegram.

### P12 — "Tutto, subito, pronto per la produzione"
Chiedere di scrivere l'intero sistema in un colpo è rischioso: la parte più incerta (YouTube raggiungibile dalla tua VM) va verificata **per prima**.

**Correzione:** si costruisce **a fasi**, ognuna funzionante, testata e salvata in git (vedi [Roadmap](roadmap.md)).

---

## 3. Verdetto sintetico

| Area | v1 | v2 |
|---|---|---|
| Idea di base | ✅ Transcript-first | ✅ Tenuta |
| Modelli/API | ❌ Gemini 2.5, generateContent | ✅ Modelli in config, Interactions API, tier flex |
| Momenti visivi | ⚠️ Scelti dal solo testo, timestamp scritti dall'AI | ✅ Segmenti numerati + "Localizza" sul video vero |
| Numeri | ⚠️ Letti dall'immagine senza distinzione | ✅ Provenienza 🗣️/👁️/🤖 verificata dal codice |
| Accesso a YouTube | ❌ Non considerato | ✅ Fallback, degrado elegante, doctor, auto-update |
| Video nuovi/live/Shorts | ❌ Non gestiti | ✅ Macchina a stati con attese e checkpoint |
| Feed | ⚠️ Solo RSS | ✅ RSS + YouTube Data API, import Takeout |
| Risparmio di tempo | ⚠️ Un report per video | ✅ + punteggio, minuti da guardare, digest, ricerca |
| Sicurezza | ⚠️ Bot "privato" non definito | ✅ Whitelist, segreti fuori da git |
| Infrastruttura | ⚠️ podman-compose | ✅ Quadlet su RHEL 9 |
| Metodo | ⚠️ Tutto insieme | ✅ A fasi, con test e commit |

La nuova architettura è descritta in [03 — Architettura](03-architettura.md); le singole scelte, con le alternative scartate, in [04 — Registro delle decisioni](04-decisioni.md).

---

## 4. Domande aperte (le risposte possono cambiare alcuni default)

1. **Dove gira la VM RHEL 9?** Casa/ufficio o cloud? (Decide se serve un proxy.) *Default scelto: casa/ufficio.*
2. **Chiave Gemini: gratuita o a pagamento?** Con il piano gratuito c'è un limite di 8 ore di video YouTube al giorno e i limiti di frequenza sono più stretti. *Default: funziona con entrambi.*
3. **Quanti canali e quanti video al giorno?** Serve per stimare costi e frequenza dei controlli. *Default: ~20 canali, ~10 video/giorno.*
4. **Dove vuoi leggere i report?** Obsidian (cartella sincronizzata), Telegram (report HTML allegato), pagina web locale? *Default: Markdown per Obsidian + HTML inviato su Telegram.*

---

## Fonti (consultate il 27/10/2026)
- Gemini — deprecazioni e modelli: <https://ai.google.dev/gemini-api/docs/deprecations>
- Gemini — prezzi: <https://ai.google.dev/gemini-api/docs/pricing>
- Gemini — comprensione video (link YouTube, ritagli, fps, risoluzione): <https://ai.google.dev/gemini-api/docs/generate-content/video-understanding> e <https://ai.google.dev/gemini-api/docs/interactions/video-understanding>
- Gemini — migrazione all'Interactions API: <https://ai.google.dev/gemini-api/docs/migrate-to-interactions>
- yt-dlp — runtime JavaScript obbligatorio (Deno, EJS): <https://github.com/yt-dlp/yt-dlp/issues/15012>
- yt-dlp — supporto Bun deprecato, Deno raccomandato (maggio 2026): <https://gigazine.net/gsc_news/en/20260525-yt-dlp-bun>
- Plugin PO token per yt-dlp: <https://pypi.org/project/bgutil-ytdlp-pot-provider>
- youtube-transcript-api (blocchi IP cloud, cookie, proxy): <https://github.com/jdepoix/youtube-transcript-api>
- Feed RSS YouTube che rispondono 404 a intermittenza: <https://discuss.ai.google.dev/t/youtube-rss-feed-endpoint-returns-404-errors/113379> e <https://feeder.co/help/rss/youtube-feeds/>
- YouTube Data API — costi delle chiamate e quota: <https://developers.google.com/youtube/v3/determine_quota_cost>
