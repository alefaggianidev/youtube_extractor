# Roadmap

Il sistema si costruisce **a fasi**. Ogni fase è utilizzabile da sola, è coperta da test ed è salvata in git.
Legenda: ✅ fatto · 🔨 in corso · ⏳ da fare

| Fase | Obiettivo | Cosa ottieni | Stato |
|---|---|---|---|
| **0 — Fondamenta** | Struttura del repository, configurazione, database, CLI, test | Il progetto si installa e si avvia | ✅ |
| **1 — MVP** | Link → trascrizione → analisi → report | `ytkb add URL` produce un report in italiano con link ai minuti | ✅ |
| **2 — Riferimenti visivi** | Localizza, cattura, lettura dei grafici | Screenshot dei grafici nel report, numeri con provenienza | ✅ |
| **3 — Automazione** | Canali seguiti, polling RSS + Data API, stati di attesa | I video nuovi vengono processati da soli | ✅ |
| **4 — Telegram** | Notifiche e invio link dal telefono | Report sul telefono appena pronti | ✅ |
| **5 — Deploy RHEL 9** | Container, Quadlet, SELinux, aggiornamenti | Il sistema gira 24/7 sulla VM | ✅ (da provare sulla tua VM) |
| **6 — Knowledge base** | Ricerca, menzioni per asset, digest giornaliero | Un messaggio al giorno al posto di 10 report | ⏳ |

## Cosa va verificato sulla VM reale
I test automatici (138) non usano la rete. Queste cose si possono verificare solo sulla tua VM, con le tue chiavi —
`ytkb doctor --deep` le prova quasi tutte in un colpo:
- [ ] YouTube raggiungibile dalla VM: metadati, sottotitoli, download di pochi secondi
- [ ] Gemini risponde con la tua chiave e il modello configurato esiste
- [ ] Build dell'immagine e avvio del servizio con Quadlet (`deploy/rhel9/install-user.sh`)
- [ ] Un primo video end-to-end → `ytkb add --now URL`
- [ ] Bot Telegram collegato alla tua chat (`ytkb telegram test`)
- [ ] Qualità dei riassunti su 3-4 video reali dei tuoi canali (eventuali ritocchi ai prompt in `src/ytkb/llm/prompts/`)

## Prossimi passi (fase 6 e oltre)
- **Digest giornaliero:** un solo messaggio al giorno con tutti i video raggruppati per asset (chi è rialzista/
  ribassista su BTC, SPX, oro…; livelli citati da più canali).
- **Ricerca nell'archivio:** "cosa hanno detto su NVDA questa settimana?" (indice full-text delle trascrizioni e
  tabella delle menzioni).
- **Rifinitura dei prompt** sui tuoi canali reali.
