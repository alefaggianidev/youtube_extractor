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
