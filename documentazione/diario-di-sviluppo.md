# Diario di sviluppo

Cosa è stato fatto, in che ordine e perché. Ogni voce dice **cosa**, **perché** e, quando serve, **un esempio**.
Le voci più recenti sono in fondo.

---

## 2026-10-27 — Sessione 1

### Passo 1 — Baseline in git
- **Cosa:** salvato il `CLAUDE.md` originale (v1) così com'era, più un file `.gitattributes`.
- **Perché:** così ogni modifica successiva al progetto è visibile come differenza nella history.
  `.gitattributes` forza i fine riga Linux (LF) nel repository: il codice girerà su RHEL 9 anche se lo modifichi da Windows.
- **Esempio:** `git diff 489c15d -- CLAUDE.md` mostra esattamente cosa è cambiato rispetto all'originale.

### Passo 2 — Verifica dello stato dell'arte (ottobre 2026)
- **Cosa:** controllati sulle fonti ufficiali modelli e prezzi Gemini, stato di yt-dlp e youtube-transcript-api, affidabilità dei
  feed RSS, quote della YouTube Data API. Installate le librerie in un ambiente di prova e **ispezionate le API reali**
  (versioni: google-genai 2.33.0, yt-dlp 2026.10.26, youtube-transcript-api 1.2.4, deno 2.9.8).
- **Perché:** il mondo YouTube cambia ogni pochi mesi; un'architettura basata su informazioni vecchie fallisce.
- **Scoperte principali:** Gemini 2.5 non è più consigliato per i nuovi progetti; `generateContent` è "legacy"; l'input da link
  YouTube può essere ritagliato con inizio/fine; yt-dlp richiede Deno; i feed RSS hanno 404 intermittenti; Deno si installa
  come pacchetto Python.

### Passo 3 — Analisi critica e architettura v2
- **Cosa:** scritti [02 — Analisi critica](02-analisi-critica-v1.md), [03 — Architettura](03-architettura.md),
  [04 — Decisioni](04-decisioni.md), [05 — Costi](05-costi.md), e riscritto il `CLAUDE.md` (v2).
- **Perché:** il v1 aveva un'ottima idea di base ma quattro punti deboli gravi (modelli superati, momenti visivi scelti senza
  guardare lo schermo, nessuna difesa dai blocchi di YouTube, nessuna gestione dei tempi di un video appena caricato).
- **Esempio della correzione più importante:** l'AI non scrive più orari come "14:20" (che spesso sbaglia): cita
  "segmento 42" e l'orario esatto lo calcola il programma.

### Passo 4 — Fase 0: le fondamenta
- **Cosa:** progetto Python gestito con `uv` (`pyproject.toml` + `uv.lock`), configurazione (`config/settings.yaml` +
  segreti in `.env`), database SQLite con la tabella `videos` che fa da coda, CLI `ytkb` con i primi comandi
  (`init`, `doctor`, `add`, `status`, `retry`, `show`) e 42 test automatici.
- **Perché:** prima di scrivere la pipeline servono basi solide: una configurazione che segnala i refusi, uno stato che
  sopravvive ai riavvii, e test che girano senza rete.
- **Esempi:**
  - un refuso in `settings.yaml` (es. `modell:` invece di `models:`) produce un errore chiaro:
    `Configurazione non valida: llm.modell: Extra inputs are not permitted`;
  - un titolo come `🔥 BTC: "settimana" decisiva? | Parte 2/3` diventa il nome di cartella
    `BTC_settimana_decisiva_Parte_2_3`, valido anche su Windows;
  - `60.000`, `60000` e `60,000` vengono riconosciuti come lo stesso numero quando verifichiamo
    che un livello sia stato davvero detto a voce;
  - `ytkb add https://youtu.be/ID` mette il video in coda con priorità alta (i link manuali passano davanti a quelli automatici).
- **Nota tecnica:** l'ambiente Python sta *fuori* dalla cartella del progetto (`UV_PROJECT_ENVIRONMENT`), così la cartella
  contiene solo file di progetto.

### Passo 5 — Fase 1: dal link al report (MVP)
- **Cosa:** la pipeline completa per un video: metadati (yt-dlp senza download) → controlli di prontezza → trascrizione
  con catena di fonti → analisi con Gemini (output JSON validato) → verifiche nel codice → report Markdown + HTML →
  indice del canale. Nuovi comandi: `ytkb add --now`, `ytkb process`, `ytkb render`, `ytkb costs`.
  Aggiunti un report di esempio (`documentazione/esempio-report/`) e la [guida all'uso](06-guida-uso.md).
- **Perché:** è la parte che dà già l'80% del valore (riassunto, minuti da guardare, livelli con provenienza);
  la parte visiva arriva nella fase 2.
- **Come abbiamo verificato l'API di Gemini senza chiave:** i test intercettano le richieste HTTP dell'SDK ufficiale e
  controllano il formato esatto inviato (es. il ritaglio `start_offset: "789.0s"` del video YouTube, il tier `flex`,
  lo schema JSON). Abbiamo anche scoperto che l'SDK riprova da solo almeno una volta dopo un errore 429: il nostro
  ripiego da `flex` a `standard` scatta dopo i suoi tentativi.
- **Esempi di comportamento coperti dai test (96 in totale):**
  - un video appena uscito senza sottotitoli → *in attesa* 15–30 minuti invece di pagare subito la trascrizione Gemini;
  - YouTube ci blocca → si passa subito alla fonte Gemini (è Google a prendere il video);
  - un livello "64.480" che non compare nella trascrizione → marcato 🤖 *non verificato*;
  - un errore di rete → riprova dopo 5, 15, 60… minuti; dopo 5 tentativi → *fallito* con il motivo;
  - un bug imprevisto non blocca il worker: il video viene rimesso in coda con "errore interno";
  - budget giornaliero superato → i video automatici aspettano il giorno dopo, quelli chiesti a mano no.
- **Controllo visivo:** il report HTML è stato verificato con screenshot su desktop (tema chiaro) e telefono (tema
  scuro); la tabella dei livelli sul telefono ora scorre dentro la sua scheda invece di uscire dallo schermo.

### Passo 6 — Fase 2: i grafici nel report
- **Cosa:** gli stadi 4-6. *Localizza*: Gemini guarda le finestre del video direttamente dal link YouTube (ritaglio
  inizio/fine, fino a 4 richieste in parallelo) e indica il secondo migliore. *Cattura*: **una sola** chiamata yt-dlp
  scarica ±1,5 secondi attorno a ogni momento (solo video, max 1080p), `ffmpeg` estrae 3 fotogrammi e teniamo il più
  nitido. *Leggi*: Gemini legge lo screenshot ad alta risoluzione con la domanda preparata dall'analisi.
  Clip MP4 opzionali.
- **Perché così:** scaricare pochi secondi espone poco ai blocchi di YouTube; guardare il video vero evita di
  catturare il momento sbagliato; leggere lo screenshot in alta risoluzione dà numeri più affidabili (comunque
  marcati 👁️ *da verificare*).
- **Esempio:** l'analisi segnala "guardate qui il supporto" nei segmenti 4-5 (finestra 00:19–00:34). Localizza
  risponde "momento migliore: 3 secondi dall'inizio della clip" → il codice calcola 00:22 → si scaricano
  00:20,5–00:23,5 → `frames/00m22s_price_chart_BTCUSD.jpg`.
- **Degrado elegante, verificato dai test:** video non pubblico → niente localizza, si cattura al momento indicato
  dalla trascrizione; YouTube blocca il download → report senza immagini ma con descrizione e link; un bug negli stadi
  visivi → il video viene comunque completato con una nota e il comando per riprovare.
- **Verifica con ffmpeg vero:** un test genera piccoli video di prova con ffmpeg (simulando i file che produrrebbe
  yt-dlp) e controlla l'estrazione dei fotogrammi e la pulizia dei file temporanei. 106 test in totale.

### Passo 7 — Fase 3: i canali che segui, in automatico
- **Cosa:** `config/channels.yaml` come elenco dei canali (aggiunta con `@nome`, import dal `subscriptions.csv` di
  Google Takeout in qualsiasi lingua, attiva/disattiva/rimuovi), controllo dei feed RSS con piano B sulla YouTube
  Data API, playlist "da riassumere", demone `ytkb run` con segnale di vita visibile in `ytkb status`.
- **Perché così:** niente OAuth sul tuo account (nessun token da rinnovare, nessun rischio); il file YAML si legge e
  si modifica a mano; l'aggiunta di canali da comando **conserva i commenti** del file.
- **Esempio:** il feed di un canale contiene 4 voci: un video nuovo, uno Short, un video di ieri e uno di un mese fa.
  Al primo controllo vanno in coda solo i 2 video recenti; lo Short viene ignorato già dal link (`/shorts/`), quello
  vecchio perché fuori dalla finestra di 48 ore. Al controllo successivo nessun duplicato.
- **Robustezza verificata dai test:** feed 404 → piano B con la Data API (se c'è la chiave), altrimenti errore
  registrato sul canale; quota esaurita → errore temporaneo; chiave sbagliata → messaggio chiaro; un errore nel
  controllo dei canali non ferma il demone; il demone si ferma in modo pulito con SIGTERM (come fa systemd).
- 126 test in totale.

### Passo 8 — Fase 4: Telegram
- **Cosa:** notifiche (riassunto breve in HTML + report completo allegato, oppure avviso di errore con il comando per
  riprovare) e bot che accetta link, `/stato`, `/start`. Comandi di configurazione `ytkb telegram chat-id` e
  `ytkb telegram test`.
- **Perché senza framework:** per un solo utente bastano tre chiamate HTTP (`getUpdates`, `sendMessage`,
  `sendDocument`); meno dipendenze, comportamento più prevedibile.
- **Esempio:** mandi al bot "guarda questo https://youtu.be/ID" → risposta "✅ In coda" → il video passa davanti a
  quelli automatici (priorità alta) → quando è pronto ricevi il riassunto **nella stessa chat**. I video scoperti in
  automatico vengono notificati a tutte le chat autorizzate.
- **Sicurezza verificata dai test:** chat non autorizzate respinte (e il video non entra in coda); in caso di errore di
  rete il messaggio non contiene l'URL con il token; se Telegram rifiuta l'HTML, il messaggio viene rimandato come testo
  semplice; se le notifiche falliscono, il video resta comunque "fatto" (con un evento che lo segnala).
- 135 test in totale.

### Passo 9 — Fase 5: pronto per la VM RHEL 9
- **Cosa:** `deploy/Containerfile` (Python 3.12 + ffmpeg + Deno dalle dipendenze, utente senza privilegi), unità
  **Quadlet** per Podman rootless (`ytkb.container`, rete privata, provider di PO token opzionale, timer di riavvio
  notturno), script `prepare-root.sh` (una volta, come root) e `install-user.sh` (installa/aggiorna, come utente
  `ytkb`), alternativa nativa con systemd, [guida di installazione](07-installazione-rhel9.md).
- **Scelte importanti:**
  - *rootless + utente dedicato*: se qualcosa va storto, non ha i permessi di root sulla VM;
  - `UserNS=keep-id`: i file in `/srv/ytkb` restano dell'utente `ytkb` (niente problemi di permessi);
  - `:Z` sul volume per SELinux *enforcing*;
  - yt-dlp aggiornato a ogni avvio del container + riavvio ogni notte: è la difesa principale contro i cambiamenti
    di YouTube;
  - nessuna porta aperta (Telegram in long polling, provider PO token solo sulla rete privata dei container).
- **Verifiche fatte qui:** gli script shell passano `shellcheck` senza avvisi; `ytkb init` funziona anche con una
  cartella dati vuota (come nel container) prendendo gli esempi dal progetto installato.
- **Da verificare sulla tua VM:** la build dell'immagine e l'avvio del servizio (qui non c'è Podman). La guida ha una
  tabella dei problemi comuni.
- Pulizia: rimosse due impostazioni che il codice non usava (`report.language`, `ytdlp.auto_update`): l'aggiornamento
  di yt-dlp ora è gestito dal container (`YTKB_UPDATE_YTDLP`).

### Passo 10 — Verifica finale
- **Rilettura del codice di yt-dlp** (invece di fidarsi della memoria) sui punti che i test non possono coprire:
  i sottotitoli vengono scritti anche senza scaricare il video ✓; `media_type` vale `livestream` anche per le dirette
  terminate, quindi le dirette si riconoscono da `live_status` (come già facevamo) ✓. Corretto: il download dei
  sottotitoli ora tollera i formati video limitati (succede proprio quando YouTube ci ostacola).
- **Prova dal vivo del comando vero** in una cartella temporanea: senza accesso a YouTube, yt-dlp fallisce → errore
  temporaneo → video rimesso in coda con attese di 5 e poi 15 minuti, motivo visibile in `ytkb status`/`ytkb show`.
  La prova ha fatto emergere due difetti, ora corretti e coperti da test:
  - i messaggi di errore di yt-dlp erano lunghi e ripetuti → ora sono ripuliti e riportati una volta sola;
  - la CLI interpretava le parentesi quadre come formattazione (`[youtube]` spariva; un titolo "[/bold]…" poteva far
    fallire la stampa) → ora il testo esterno viene stampato così com'è; anche nei link Markdown dei report le
    parentesi quadre dei titoli sono protette.
- **Nuovo:** `ytkb doctor --deep` prova davvero YouTube (metadati, sottotitoli, 3 secondi di video) e Gemini
  (una chiamata minuscola): è il primo comando da lanciare sulla VM. `ytkb channels import-takeout --disabled`
  per importare le iscrizioni disattivate e attivare solo i canali di finanza.
- **Stato:** 141 test, lint pulito. Non verificabile da qui: accesso reale a YouTube e Gemini dalla tua rete, build
  dell'immagine con Podman (vedi checklist nella [roadmap](roadmap.md)).
