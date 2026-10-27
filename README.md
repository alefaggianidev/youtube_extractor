# yt-finance-kb (`ytkb`)

Sistema personale che **guarda i video YouTube di finanza e trading al posto tuo** e ti consegna un report in italiano:
riassunto, "vale la pena guardarlo?", livelli e setup con la **provenienza di ogni numero**, e gli **screenshot dei grafici**
nei momenti in cui chi parla li indica. Funziona con link passati a mano (terminale o Telegram) e in automatico sui
canali a cui sei iscritto. Pensato per girare su una VM **RHEL 9**.

- 📚 **Documentazione semplice, con esempi:** [`documentazione/`](documentazione/README.md)
- 🧭 **Come funziona (esempio completo):** [`documentazione/01-cosa-fa-il-sistema.md`](documentazione/01-cosa-fa-il-sistema.md)
- 🏗️ **Architettura:** [`documentazione/03-architettura.md`](documentazione/03-architettura.md)
- 🗺️ **A che punto siamo:** [`documentazione/roadmap.md`](documentazione/roadmap.md)

## Avvio rapido (sviluppo o prova sul PC)

```bash
uv sync                                       # installa tutto (Python 3.12, yt-dlp, Deno, ...)
uv run ytkb init                              # crea config/settings.yaml, config/channels.yaml, .env
# inserisci GEMINI_API_KEY nel file .env
uv run ytkb doctor --deep                     # verifica che YouTube e Gemini siano raggiungibili
uv run ytkb add --now https://youtu.be/ID     # primo report
```

- 📖 **Guida all'uso (con esempi):** [`documentazione/06-guida-uso.md`](documentazione/06-guida-uso.md)
- 🖥️ **Installazione sulla VM RHEL 9:** [`documentazione/07-installazione-rhel9.md`](documentazione/07-installazione-rhel9.md)
- 🧾 **Com'è fatto un report:** [`documentazione/esempio-report/report.md`](documentazione/esempio-report/report.md)

> Stato: fasi 0–5 completate e coperte da test automatici (senza rete). Da verificare sulla VM reale: accesso a
> YouTube dalla rete della VM e prima chiamata a Gemini con la tua chiave (`ytkb doctor --deep`).
