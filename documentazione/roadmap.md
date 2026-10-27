# Roadmap

Il sistema si costruisce **a fasi**. Ogni fase è utilizzabile da sola, è coperta da test ed è salvata in git.
Legenda: ✅ fatto · 🔨 in corso · ⏳ da fare

| Fase | Obiettivo | Cosa ottieni | Stato |
|---|---|---|---|
| **0 — Fondamenta** | Struttura del repository, configurazione, database, CLI, test | Il progetto si installa e si avvia | ✅ |
| **1 — MVP** | Link → trascrizione → analisi → report | `ytkb add URL` produce un report in italiano con link ai minuti | ✅ |
| **2 — Riferimenti visivi** | Localizza, cattura, lettura dei grafici | Screenshot dei grafici nel report, numeri con provenienza | ✅ |
| **3 — Automazione** | Canali seguiti, polling RSS + Data API, stati di attesa | I video nuovi vengono processati da soli | ✅ |
| **4 — Telegram** | Notifiche e invio link dal telefono | Report sul telefono appena pronti | 🔨 |
| **5 — Deploy RHEL 9** | Container, Quadlet, SELinux, aggiornamenti | Il sistema gira 24/7 sulla VM | ⏳ |
| **6 — Knowledge base** | Ricerca, menzioni per asset, digest giornaliero | Un messaggio al giorno al posto di 10 report | ⏳ |

## Cosa va verificato sulla VM reale
I test automatici non usano la rete. Queste cose si possono verificare solo sulla tua VM, con le tue chiavi:
- [ ] YouTube raggiungibile dalla VM (trascrizioni e metadati) → `ytkb doctor`
- [ ] Gemini risponde con la tua chiave → `ytkb doctor`
- [ ] Un primo video end-to-end → `ytkb add URL --now`
- [ ] Cattura frame (download di sezioni) funzionante dalla VM
- [ ] Bot Telegram collegato alla tua chat
