# 01 — Cosa fa il sistema (spiegato con un esempio)

## Il problema
Segui una ventina di canali YouTube di trading e finanza. Escono 8–10 video al giorno, da 15 minuti a 2 ore.
Guardarli tutti richiede ore, ma spesso le informazioni davvero utili di un video stanno in 3–5 minuti.

## La soluzione in una frase
Un assistente che **guarda i video al posto tuo** e ti consegna un riassunto in italiano, con **gli screenshot dei grafici
nei punti in cui chi parla li indica**, e ti dice **se e quali minuti vale la pena guardare**.

## Un esempio dall'inizio alla fine
*(Esempio inventato a scopo illustrativo: canale, video e numeri non sono reali.)*

**18:02** — Il canale *"Trading Facile"* carica **"BTC e S&P500: settimana decisiva"** (42 minuti).

**18:15** — Il sistema controlla i feed dei tuoi canali (ogni 15 minuti) e trova il video nuovo. Lo mette in coda.

**18:15** — *Controllo prontezza*: non è una live, non è uno Short, dura 42 minuti (entro i limiti).
I sottotitoli automatici però non sono ancora pronti → stato **in attesa**, riprova tra 20 minuti.

**18:35** — Sottotitoli pronti. Il sistema scarica **solo il testo** (circa 40 KB) e lo divide in segmenti numerati:

```text
[S041 12:58] adesso passiamo a bitcoin timeframe giornaliero
[S042 13:12] come vedete qui il prezzo è tornato sul supporto dei 60.000
[S043 13:27] se lo perdiamo in chiusura daily il prossimo livello è 56.500
```

**18:36** — *Analisi*: Gemini legge il testo e risponde con dati strutturati, per esempio:
"asset BTCUSD, rialzista, timeframe giornaliero, supporto 60.000 detto nel segmento 42; momento visivo importante nei
segmenti 42–43: chiedere *quali livelli sono disegnati sul grafico*".
Nota: il modello cita **"segmento 42"**, non un orario. L'orario esatto (13:12) lo calcola il programma.

**18:37** — *Localizza*: il sistema chiede a Gemini di guardare **solo** la finestra 13:09–13:30 del video, direttamente su
YouTube. Risposta: *"Grafico giornaliero BTCUSD; linea orizzontale a 60.000; il momento più chiaro è 13:18"*.

**18:37** — *Cattura*: scarica **3 secondi** di video (13:17–13:20) in 1080p, estrae 3 fotogrammi e tiene il più nitido →
`frames/13m18s_price_chart_BTCUSD.jpg`.

**18:38** — *Lettura*: Gemini legge lo screenshot in alta risoluzione: *"linee a 60.000 e 64.480"*.

**18:38** — Ti arriva su Telegram:

> 📈 **BTC e S&P500: settimana decisiva** — Trading Facile · 42 min
> ⚡ BTC rialzista finché tiene 60.000 in chiusura giornaliera; sotto, obiettivo 56.500. S&P500 neutrale in attesa del CPI.
> 🎯 Vale la pena guardarlo? **3/5** — guarda 12:58–18:40 (setup BTC).
> 📎 report completo in allegato (HTML)

E nel report completo trovi, per esempio:

> ### BTCUSD — 🟢 Rialzista (1D)
> - Supporto **60.000** 🗣️ [13:12](https://youtu.be/VIDEO_ID?t=792)
> - Obiettivo se rompe **56.500** 🗣️ [13:27](https://youtu.be/VIDEO_ID?t=807)
> - Resistenza **64.480** 👁️ *letto dal grafico — da verificare*
>
> ![BTCUSD giornaliero](frames/13m18s_price_chart_BTCUSD.jpg)

I simboli dicono **da dove viene ogni numero**: 🗣️ detto a voce (verificato nella trascrizione), 👁️ letto dal grafico
(da controllare sullo screenshot accanto), 🤖 dedotto e non verificato.

## Come gli passi i video
1. **Automatico:** i canali che segui (importati dalle tue iscrizioni YouTube).
2. **Dal PC:** `ytkb add https://youtu.be/VIDEO_ID`
3. **Dal telefono:** incolli il link nella chat con il tuo bot Telegram.

## Cosa NON fa
- **Non dà consigli di investimento:** riporta cosa dice il video, con la provenienza di ogni numero.
- **Non scarica video interi:** solo pochi secondi per ogni screenshot.
- **Non funziona con video privati o per soli membri** (per ora).
- **Non è infallibile:** i numeri 👁️ letti dai grafici vanno verificati, e una trascrizione automatica può sbagliare un ticker.
