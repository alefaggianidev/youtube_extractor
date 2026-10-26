# 📚 Documentazione di yt-finance-kb

Questa cartella spiega **in modo semplice e con esempi** cosa stiamo costruendo, come funziona e perché abbiamo fatto certe
scelte. Se hai 5 minuti, leggi solo i primi due documenti.

## Da dove iniziare

| # | Documento | Cosa trovi | Tempo |
|---|---|---|---|
| 1 | [01 — Cosa fa il sistema](01-cosa-fa-il-sistema.md) | Il sistema spiegato con un esempio, dall'upload al report | 5 min |
| 2 | [02 — Analisi critica del v1](02-analisi-critica-v1.md) | Cosa andava bene nel CLAUDE.md originale, cosa no, come l'abbiamo corretto | 10 min |
| 3 | [03 — Architettura](03-architettura.md) | Gli 8 stadi con esempi di input/output e diagrammi | 15 min |
| 4 | [04 — Registro delle decisioni](04-decisioni.md) | Ogni scelta tecnica, con le alternative scartate | consultazione |
| 5 | [05 — Quanto costa](05-costi.md) | Stima dei costi con i calcoli | 3 min |
| 6 | [Roadmap](roadmap.md) | Le fasi di sviluppo e a che punto siamo | 2 min |
| 7 | [Diario di sviluppo](diario-di-sviluppo.md) | Cosa è stato fatto, passo per passo, e perché | consultazione |
| 8 | [Glossario](glossario.md) | Le parole tecniche spiegate semplici | consultazione |

Arriveranno con le rispettive fasi: guida all'uso quotidiano, configurazione, installazione su RHEL 9.

## Il sistema in 30 secondi
- **Tu** ti iscrivi ai canali YouTube come sempre (o mandi un link al bot).
- **Il sistema**, quando esce un video nuovo, lo *ascolta* (trascrizione), lo *capisce* (analisi con un modello AI),
  *guarda* solo i momenti in cui chi parla mostra un grafico, cattura lo screenshot e ti manda un report in italiano.
- **Risultato:** in 30 secondi sai cosa dice il video e se vale la pena guardarlo.

## Come è organizzata
- I documenti numerati (`01`–`05`) spiegano il progetto e cambiano poco.
- La **roadmap** e il **diario** vengono aggiornati a ogni passo di sviluppo.
- Tutto è versionato in git insieme al codice: la storia dei cambiamenti è nella history del repository.
