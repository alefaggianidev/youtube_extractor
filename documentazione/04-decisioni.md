# 04 — Registro delle decisioni

Ogni scelta tecnica importante ha una scheda: **contesto → decisione → alternative scartate → conseguenze**.
Regola: una decisione non si cambia "di nascosto": si aggiunge una nuova scheda che la sostituisce.

| ID | Decisione | Stato |
|---|---|---|
| D-001 | Transcript-first | ✅ attiva (dal v1) |
| D-002 | Gemini come provider, dietro un'interfaccia; Interactions API; modelli in config | ✅ attiva |
| D-003 | L'LLM cita segmenti, non timestamp | ✅ attiva |
| D-004 | Stadio "Localizza" su link YouTube, senza download | ✅ attiva |
| D-005 | Provenienza obbligatoria dei numeri | ✅ attiva |
| D-006 | Catena di fallback per la trascrizione | ✅ attiva |
| D-007 | SQLite come stato e coda | ✅ attiva |
| D-008 | Macchina a stati + checkpoint per stadio | ✅ attiva |
| D-009 | RSS + fallback YouTube Data API; iscrizioni da Takeout/@handle | ✅ attiva |
| D-010 | Telegram con chiamate HTTP dirette e whitelist | ✅ attiva |
| D-011 | Pillow + numpy al posto di OpenCV | ✅ attiva |
| D-012 | Quadlet in produzione su RHEL 9 | ✅ attiva |
| D-013 | Deno installato come pacchetto Python | ✅ attiva |
| D-014 | Clip video opzionali, default link al secondo | ✅ attiva |
| D-015 | Doppio report: Markdown (Obsidian) + HTML autocontenuto | ✅ attiva |
| D-016 | Lingue: codice in inglese, testi in italiano | ✅ attiva |
| D-017 | Service tier "flex" di default | ✅ attiva |

---

### D-001 — Transcript-first
- **Contesto:** un'ora di video come testo costa ~15.000 token, come video 360.000–1.000.000.
- **Decisione:** l'analisi principale si fa sul testo; il video si guarda solo nei momenti selezionati.
- **Alternative scartate:** far guardare a Gemini l'intero video (più semplice, ma 20–60 volte più token e limitato ai video pubblici entro ~1–3 ore).
- **Conseguenze:** serve una trascrizione affidabile → D-006.

### D-002 — Gemini dietro un'interfaccia
- **Contesto:** Gemini è l'unico modello che accetta direttamente **link YouTube** (anche ritagliati con inizio/fine). Google ha introdotto l'Interactions API e marcato `generateContent` come *legacy*. I modelli cambiano ogni pochi mesi (2.5 → 3.x).
- **Decisione:** un'interfaccia `LLMProvider` con un'implementazione Gemini (Interactions API, SDK `google-genai`) e una finta per i test. I nomi dei modelli stanno in `config/settings.yaml`.
- **Alternative scartate:** Claude o GPT come provider principale (ottimi sul testo ma senza ingestione diretta di YouTube); più provider dal giorno 1 (complessità senza beneficio immediato).
- **Conseguenze:** aggiungere un altro provider = un nuovo file in `llm/`, senza toccare la pipeline.

### D-003 — Segmenti, non timestamp
- **Contesto:** gli LLM sbagliano i timestamp nei testi lunghi.
- **Decisione:** trascrizione inviata come `[S042 13:12] testo`; l'output cita `segment_id`; i secondi li calcola il codice.
- **Alternative scartate:** timestamp `MM:SS` scritti dall'LLM (v1).
- **Conseguenze:** link precisi al secondo; validazione semplice (un ID o esiste o no).

### D-004 — "Localizza" sul link YouTube
- **Contesto:** dal solo testo non si sa cosa c'è sullo schermo; scaricare per "guardare" espone ai blocchi di YouTube.
- **Decisione:** per ogni momento visivo, Gemini guarda la finestra di video passata come link YouTube con `start_offset`/`end_offset` (modalità *static*), e indica il secondo migliore.
- **Alternative scartate:** euristiche OpenCV (v1), scaricare l'intero video a bassa risoluzione.
- **Conseguenze:** funziona solo con video **pubblici**; la funzione è in *preview* (prezzi e limiti possono cambiare) → è opzionale e degradabile.

### D-005 — Provenienza dei numeri
- **Contesto:** in finanza un numero inventato è pericoloso.
- **Decisione:** ogni numero è 🗣️ *detto a voce* (verificato nella trascrizione dal codice), 👁️ *letto dal grafico* o 🤖 *non verificato*.
- **Conseguenze:** l'LLM deve restituire le parole esatte (`spoken_text`) con cui il numero è stato detto.

### D-006 — Catena di fallback per la trascrizione
- **Contesto:** youtube-transcript-api è bloccata sugli IP cloud e usa un'API non documentata.
- **Decisione:** `transcript_api → ytdlp_subs → gemini_url → (audio)`, ordine configurabile, con attesa iniziale per i sottotitoli automatici.
- **Conseguenze:** il sistema sopravvive al blocco di una singola fonte.

### D-007 — SQLite come stato e coda
- **Contesto:** un utente, decine di video al giorno.
- **Decisione:** SQLite in modalità WAL: tabelle `videos`, `channels`, `events`, `llm_calls`. La coda è la tabella `videos`.
- **Alternative scartate:** Redis + Celery, PostgreSQL (servizi in più da gestire, nessun beneficio a questa scala).
- **Conseguenze:** backup = copiare un file.

### D-008 — Macchina a stati + checkpoint
- **Decisione:** stati `queued / waiting / processing / done / skipped / failed`; ogni stadio salva un artefatto con scrittura atomica (file temporaneo + rinomina); uno stadio con artefatto valido viene saltato.
- **Conseguenze:** riprendere dopo un errore non costa nulla; `ytkb render` rigenera il report senza chiamare l'LLM.

### D-009 — RSS + YouTube Data API
- **Contesto:** RSS gratuito ma con 404 intermittenti e solo 15 voci.
- **Decisione:** RSS come fonte primaria; se fallisce e c'è `YOUTUBE_API_KEY`, `playlistItems.list` sulla playlist "uploads" (1 unità di quota). Canali da `config/channels.yaml`, importabili da Google Takeout o con `@handle`.
- **Alternative scartate:** OAuth sul tuo account (token da rinnovare, rischi inutili); WebSub/PubSubHubbub (richiede un indirizzo pubblico raggiungibile).

### D-010 — Telegram con HTTP diretto
- **Decisione:** `getUpdates` (long polling), `sendMessage`, `sendDocument` via `httpx`. Solo i `chat_id` in whitelist possono usare il bot.
- **Alternative scartate:** `aiogram` (framework asincrono: eccessivo per un utente).
- **Conseguenze:** nessuna porta aperta sulla VM.

### D-011 — Pillow + numpy al posto di OpenCV
- **Decisione:** nitidezza = varianza del Laplaciano calcolata con numpy; frame uniformi = deviazione standard bassa.
- **Conseguenze:** immagine container più leggera, meno dipendenze native su RHEL.

### D-012 — Quadlet su RHEL 9
- **Decisione:** in produzione un file `.container` gestito da systemd (riavvio automatico, log in journald); volumi con `:Z` per SELinux. `compose.yaml` solo come comodità di sviluppo.
- **Alternative scartate:** podman-compose in produzione (strumento EPEL, non nativo).

### D-013 — Deno come pacchetto Python
- **Contesto:** yt-dlp richiede Deno per YouTube; su RHEL non è nei repository standard.
- **Decisione:** dipendenza `deno` da PyPI (porta il binario dentro l'ambiente Python) + `yt-dlp[default]` (include `yt-dlp-ejs`). Il percorso di Deno viene passato a yt-dlp in modo esplicito.
- **Conseguenze:** `uv sync` installa tutto, anche fuori dal container.

### D-014 — Clip opzionali
- **Decisione:** default solo screenshot + link `https://youtu.be/ID?t=798`. Clip H.264 attivabili in config (utili se i video vengono cancellati).

### D-015 — Doppio report
- **Decisione:** un unico *view-model* → `report.md` (Obsidian, link relativi, front matter YAML) e `report.html` (immagini incorporate, leggibile ovunque).

### D-016 — Lingue
- **Decisione:** identificatori del codice in inglese; commenti, docstring, prompt, report e documentazione in italiano.

### D-017 — Service tier "flex"
- **Contesto:** il tier flex costa la metà; i report non sono urgenti.
- **Decisione:** `llm.service_tier: flex` di default; in caso di errore temporaneo si può ripiegare su `standard` (`flex_fallback_to_standard: true`).
