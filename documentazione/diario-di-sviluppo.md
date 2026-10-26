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
