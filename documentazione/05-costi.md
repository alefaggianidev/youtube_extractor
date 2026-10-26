# 05 — Quanto costa

> **Stima:** circa **3–10 centesimi di dollaro per video** con i prezzi di ottobre 2026 → con 10 video al giorno
> **9–29 $/mese**. Dal **1° gennaio 2027** il listino di Gemini 3.8 Flash indica il **raddoppio** dei prezzi.

Prezzi usati (Gemini, piano a pagamento, dollari per milione di token — fonte: pagina prezzi ufficiale, 27/10/2026):

| Modello | Input | Output (incl. "ragionamento") | Note |
|---|---|---|---|
| `gemini-3.8-flash` | 0,75 | 3,75 | default; raddoppio annunciato dal 01/01/2027 |
| `gemini-3.5-flash-lite` | 0,30 | 2,50 | alternativa economica per l'analisi |
| Tier **flex** | −50% | −50% | più lento, ideale per noi |

L'input da **link YouTube** è dichiarato in *preview* e attualmente gratuito: nel calcolo lo consideriamo comunque a pagamento,
per prudenza.

## Calcolo per un video di 40 minuti

| Passaggio | Token in input | Token in output | Costo standard | Costo flex |
|---|---|---|---|---|
| Analisi del testo | ~11.500 (trascrizione ~9.000 + istruzioni) | ~4.000 | 0,024 $ | 0,012 $ |
| Localizza (8 finestre × 20 s × ~290 token/s) | ~46.000 | ~4.000 | 0,050 $ | 0,025 $ |
| Lettura frame (8 immagini alta risoluzione) | ~12.000 | ~3.200 | 0,021 $ | 0,011 $ |
| **Totale** | | | **~0,095 $** | **~0,048 $** |

Se l'input YouTube resta gratuito, "Localizza" scende a ~0,008 $ (flex) e il totale a **~0,03 $**.

**Esempio mensile** (10 video al giorno, flex): 0,03–0,05 $ × 300 video ≈ **9–15 $/mese**; senza flex ≈ 29 $/mese.
Dal 2027, a prezzi raddoppiati: ~18–58 $/mese.

## Come teniamo sotto controllo la spesa
- `llm.daily_budget_usd`: oltre la soglia i video restano in coda fino al giorno dopo.
- `visual.max_triggers`: massimo momenti visivi per video (default 8).
- `filters`: salta Shorts, video troppo corti o troppo lunghi; impostazioni diverse per canale.
- Ogni chiamata viene registrata nella tabella `llm_calls` (modello, token, costo stimato): `ytkb costs` mostra il riepilogo.
- I prezzi sono in `config/settings.yaml` (`llm.pricing`): se Google li cambia, si aggiornano lì.

## Altri costi
- **YouTube Data API:** gratuita entro 10.000 unità/giorno (ne usiamo al massimo qualche migliaio, e solo se l'RSS fallisce).
- **Telegram:** gratuito.
- **Proxy residenziale:** solo se la VM è in cloud e YouTube la blocca (tipicamente pochi dollari/GB).
