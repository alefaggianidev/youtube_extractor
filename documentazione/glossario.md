# Glossario

Le parole tecniche usate nel progetto, spiegate in modo semplice. In ordine alfabetico.

| Termine | Significato semplice | Esempio nel progetto |
|---|---|---|
| **API** | Un "telefono" con cui un programma chiede dati o servizi a un altro. | Chiediamo a Gemini di analizzare un testo. |
| **API key** | Una password che identifica il tuo programma presso un servizio. | `GEMINI_API_KEY` nel file `.env`. |
| **Artefatto** | Il file prodotto da uno stadio della pipeline. | `analysis.json` è l'artefatto dello stadio "analisi". |
| **Backoff** | Aspettare sempre di più tra un tentativo e l'altro dopo un errore. | 5, 15, 60, 180, 720 minuti. |
| **Bias** | La direzione di mercato attesa da chi parla. | Rialzista (bullish), ribassista (bearish), neutrale. |
| **Checkpoint** | Un punto di salvataggio: se qualcosa fallisce, si riparte da lì. | Se fallisce la cattura dei frame, l'analisi già fatta non si rifà. |
| **CLI** | Programma da usare con comandi scritti nel terminale. | `ytkb add https://youtu.be/...` |
| **Container** | Una "scatola" che contiene il programma con tutto ciò che gli serve, isolata dal sistema. | Il container `ytkb` contiene Python, ffmpeg, Deno. |
| **Deep link** | Un link che apre il video a un secondo preciso. | `https://youtu.be/ID?t=792` apre a 13:12. |
| **Degrado elegante** | Se una parte opzionale fallisce, il resto funziona lo stesso. | Niente screenshot? Il report esce con la descrizione e il link. |
| **Deno** | Un motore JavaScript. yt-dlp lo usa per risolvere i "rompicapo" che YouTube mette nella pagina. | Installato come pacchetto Python. |
| **Digest** | Un riassunto di più video in un unico messaggio. | "Oggi 6 video: BTC 4 rialzisti, 2 ribassisti". |
| **Fallback** | Il piano B quando il piano A non funziona. | Se l'RSS non risponde, usiamo la YouTube Data API. |
| **Feed RSS** | Un indirizzo che elenca gli ultimi contenuti di un sito, leggibile da un programma. | `.../feeds/videos.xml?channel_id=UC...` |
| **ffmpeg** | Il "coltellino svizzero" per audio e video da riga di comando. | Estrae i fotogrammi dai pezzetti di video. |
| **Flex (tier)** | Modalità di Gemini più lenta ma a metà prezzo. | Default per i nostri report. |
| **Frame / fotogramma** | Una singola immagine di un video. | Lo screenshot del grafico. |
| **JSON** | Un formato di testo per dati strutturati, leggibile da programmi e persone. | `{"asset": "BTCUSD", "bias": "BULLISH"}` |
| **Knowledge base (KB)** | Un archivio interrogabile di tutto ciò che è stato analizzato. | "Cosa hanno detto su NVDA questa settimana?" |
| **Laplaciano (varianza del)** | Una misura matematica di quanto è nitida un'immagine: più bordi netti = valore più alto. | Scegliamo il frame con il valore più alto. |
| **LLM** | *Large Language Model*: il modello AI che legge e scrive testo (qui Gemini). | |
| **Long polling** | Il programma chiede a Telegram "ci sono messaggi?" e Telegram risponde appena ce n'è uno. | Così la VM non deve esporre porte su Internet. |
| **Macchina a stati** | Un elenco preciso di "stati" in cui può trovarsi un video e di come si passa dall'uno all'altro. | in coda → in lavorazione → fatto. |
| **Obsidian** | Un'app per note in Markdown, ottima per un archivio personale. | Apri la cartella `archive` come "vault". |
| **OAuth** | Il meccanismo "Accedi con Google" per dare a un'app accesso al tuo account. | Lo **evitiamo**: non serve. |
| **PO token** | "Prova di origine": un gettone che YouTube richiede per dimostrare che la richiesta viene da un vero browser/app. | Plugin opzionale `bgutil` per yt-dlp. |
| **Premiere** | Video annunciato in anticipo e trasmesso a un orario fissato. | Compare nel feed prima di essere visibile: va atteso. |
| **Prompt** | Le istruzioni che diamo all'LLM. | `src/ytkb/llm/prompts/analysis_system.md` |
| **Provenienza** | Da dove viene un numero del report. | 🗣️ detto a voce, 👁️ letto dal grafico, 🤖 non verificato. |
| **Proxy residenziale** | Un intermediario con IP "di casa", che YouTube blocca meno di quelli dei server. | Serve solo se la VM è in cloud. |
| **Pydantic** | Libreria Python che controlla che i dati abbiano la forma giusta. | Valida il JSON restituito da Gemini. |
| **Quadlet** | Il modo nativo di RHEL per far gestire un container a systemd come un servizio. | `ytkb.container` |
| **Quota** | Il numero massimo di operazioni gratuite al giorno su un'API. | YouTube Data API: 10.000 unità/giorno. |
| **Segmento** | Un pezzo di trascrizione di ~20 secondi con un numero e un orario. | `[S042 13:12] come vedete qui...` |
| **SELinux** | Il sistema di sicurezza di RHEL che decide chi può accedere a cosa. | Per questo i volumi del container hanno `:Z`. |
| **Short** | Video verticale breve (fino a 3 minuti). | Saltati di default. |
| **SQLite** | Un database contenuto in un singolo file, senza server. | `data/state/ytkb.db` |
| **systemd** | Il gestore dei servizi di Linux: avvia, riavvia e registra i log dei programmi. | |
| **Ticker** | La sigla di uno strumento finanziario. | BTCUSD, SPX, XAUUSD, NVDA. |
| **Token** | L'unità con cui gli LLM misurano (e fanno pagare) il testo: circa 3/4 di parola. | 1 ora di parlato ≈ 15.000 token. |
| **Trascrizione** | Il testo di ciò che viene detto nel video, con i tempi. | `transcript.txt` |
| **uv** | Gestore veloce di ambienti e dipendenze Python. | `uv sync`, `uv run ytkb ...` |
| **Webhook / WebSub** | Il servizio *ti chiama* quando c'è una novità (invece di chiedere tu). | Scartato: richiede un indirizzo pubblico. |
| **yt-dlp** | Il programma open source più usato per leggere informazioni e scaricare da YouTube. | Metadati, sottotitoli, pezzetti di video. |
