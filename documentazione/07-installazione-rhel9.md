# 07 — Installazione sulla VM RHEL 9

> **In breve:** il sistema gira in un **container Podman** gestito da **systemd** (Quadlet), con un utente dedicato
> senza privilegi. Nessuna porta da aprire. Tempo: ~20 minuti la prima volta.

```mermaid
flowchart LR
    A["1 · Copia il progetto<br/>sulla VM"] --> B["2 · Preparazione<br/>(root, una volta)"]
    B --> C["3 · Installazione<br/>(utente ytkb)"]
    C --> D["4 · Chiavi e<br/>configurazione"]
    D --> E["5 · Avvio e<br/>verifica"]
```

## Requisiti
- RHEL 9.2 o successiva (serve Podman ≥ 4.4 per Quadlet; RHEL 9 lo include).
- 2 vCPU, 2–4 GB di RAM, 20 GB di disco (l'archivio cresce di pochi MB per video).
- Accesso a Internet verso: PyPI, YouTube, `generativelanguage.googleapis.com` (Gemini), `api.telegram.org`.
- **Dove sta la VM conta:** a casa o in ufficio YouTube di solito non blocca; in cloud (AWS, Azure, Hetzner…) è
  probabile che serva un proxy (vedi [Se YouTube blocca la VM](#se-youtube-blocca-la-vm)).

## 1. Copia il progetto sulla VM
**Con git** (consigliato): dal PC fai `git push` del repository, poi sulla VM (dopo il passo 2, come utente `ytkb`):

```bash
git clone https://github.com/alefaggianidev/youtube_extractor.git
```

Se il repository è privato, serve un *personal access token* di GitHub (o una deploy key SSH).
**Senza git:** copia la cartella con `scp -r youtube_extractor ytkb@VM:~/` (escludendo `data/` e `.env`).

## 2. Preparazione (root, una volta sola)

```bash
sudo bash youtube_extractor/deploy/rhel9/prepare-root.sh
```

Cosa fa: installa `podman` e `git`, crea l'utente di servizio `ytkb`, crea `/srv/ytkb` (dati e configurazione) e
abilita il *linger* (i servizi dell'utente partono all'avvio della VM anche senza login).

> Se hai copiato il progetto nella home di un altro utente, spostalo in `/home/ytkb/` e dai la proprietà:
> `sudo chown -R ytkb:ytkb /home/ytkb/youtube_extractor`

## 3. Installazione (utente ytkb)

```bash
sudo -iu ytkb
bash youtube_extractor/deploy/rhel9/install-user.sh
```

Al **primo** lancio lo script costruisce l'immagine (qualche minuto), installa le unità systemd e crea la
configurazione in `/srv/ytkb`, poi si ferma chiedendoti di compilarla.

## 4. Chiavi e configurazione

```bash
nano /srv/ytkb/.env                  # GEMINI_API_KEY obbligatoria; TELEGRAM_BOT_TOKEN, YOUTUBE_API_KEY facoltative
nano /srv/ytkb/config/settings.yaml  # es. telegram.enabled / allowed_chat_ids, budget giornaliero
```

Canali: copia il tuo `subscriptions.csv` di Google Takeout in `/srv/ytkb/` e, dopo l'avvio (passo 5):

```bash
podman exec ytkb ytkb channels import-takeout /srv/ytkb/subscriptions.csv
podman exec ytkb ytkb channels list
```

## 5. Avvio e verifica

```bash
bash youtube_extractor/deploy/rhel9/install-user.sh   # secondo lancio: avvia il servizio
podman exec ytkb ytkb doctor                         # tutto OK?
podman exec ytkb ytkb add --now https://youtu.be/ID  # primo video di prova
journalctl --user -u ytkb -f                         # log in tempo reale (Ctrl+C per uscire)
```

I report finiscono in `/srv/ytkb/data/archive/`. Con Telegram configurato arrivano anche sul telefono.

## Comandi di tutti i giorni

| Cosa | Comando (utente ytkb) |
|---|---|
| Stato della coda | `podman exec ytkb ytkb status` |
| Analizzare un video adesso | `podman exec ytkb ytkb add --now <link>` |
| Log | `journalctl --user -u ytkb -f` |
| Riavviare | `systemctl --user restart ytkb` |
| Fermare / avviare | `systemctl --user stop ytkb` / `systemctl --user start ytkb` |
| Spesa AI | `podman exec ytkb ytkb costs` |

## Aggiornamenti
- **yt-dlp** si aggiorna da solo: a ogni avvio del container e ogni notte alle ~05:10 (timer `ytkb-update`).
- **Il codice:** `cd ~/youtube_extractor && git pull && bash deploy/rhel9/install-user.sh`.

## Backup
Basta copiare `/srv/ytkb` (configurazione, `.env`, database `data/state/ytkb.db`, archivio dei report). Esempio:

```bash
tar czf ytkb-backup-$(date +%F).tgz -C /srv ytkb
```

## Leggere i report dal PC (Obsidian)
Sincronizza `/srv/ytkb/data/archive` con il PC (es. **Syncthing**, oppure `rsync`/`scp` periodico) e apri la cartella
come *vault* di Obsidian. In alternativa ti bastano i report HTML che arrivano su Telegram.

## Se YouTube blocca la VM
Sintomi: in `ytkb status` o nei log compaiono *"Sign in to confirm you're not a bot"*, *"BLOCCATO"*, *"PO token"*.
1. **Proxy** (soprattutto se la VM è in cloud): in `/srv/ytkb/.env` metti `YTKB_PROXY=http://utente:password@host:porta`
   (un proxy *residenziale*; quelli dei datacenter vengono bloccati anche loro).
2. **Provider di PO token:**

   ```bash
   WITH_POT=1 bash youtube_extractor/deploy/rhel9/install-user.sh
   ```

   e in `/srv/ytkb/config/settings.yaml`:

   ```yaml
   ytdlp:
     extractor_args:
       youtubepot-bgutilhttp: {base_url: ["http://bgutil-pot:4416"]}
   ```

3. **Cookie:** solo come ultima risorsa e **solo di un account Google secondario**, mai del tuo account principale.

Anche quando YouTube blocca i download, il sistema continua a produrre i report: la trascrizione la fa Gemini dal link
del video e al posto degli screenshot trovi la descrizione e il link al secondo esatto.

## Problemi comuni

| Sintomo | Causa probabile | Soluzione |
|---|---|---|
| `systemctl --user` dice "Failed to connect to bus" | sessione aperta con `su` | entra con `sudo -iu ytkb` (o `export XDG_RUNTIME_DIR=/run/user/$(id -u)`) |
| Il servizio `ytkb` non esiste | Quadlet non ha generato l'unità | `/usr/libexec/podman/quadlet -dryrun -user` mostra l'errore nel file `.container` |
| "Permission denied" su `/srv/ytkb` | proprietario sbagliato | `sudo chown -R ytkb:ytkb /srv/ytkb` |
| Blocchi SELinux | volume senza `:Z` o etichetta errata | `sudo ausearch -m avc -ts recent`; il file Quadlet usa già `:Z` |
| `GEMINI_API_KEY mancante` | `.env` non compilato | modifica `/srv/ytkb/.env`, poi `systemctl --user restart ytkb` |
| Gemini: "Modello o risorsa inesistente" | modello ritirato | aggiorna `llm.models` in `settings.yaml` (vedi pagina modelli di Google) |
| Feed RSS 404 | problema intermittente di YouTube | si risolve da solo; con `YOUTUBE_API_KEY` scatta il piano B |

## Installazione nativa (senza container)
Possibile ma più laboriosa su RHEL (ffmpeg non è nei repository standard):

```bash
sudo subscription-manager repos --enable codeready-builder-for-rhel-9-$(arch)-rpms
sudo dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm
sudo dnf install -y https://mirrors.rpmfusion.org/free/el/rpmfusion-free-release-$(rpm -E %rhel).noarch.rpm
sudo dnf install -y ffmpeg git python3.12
# come utente ytkb:
curl -LsSf https://astral.sh/uv/install.sh | sh
cd ~/youtube_extractor && UV_PROJECT_ENVIRONMENT=~/.venvs/ytkb uv sync --frozen --no-dev && uv run ytkb init
cp deploy/native/ytkb.service ~/.config/systemd/user/ && systemctl --user daemon-reload && systemctl --user enable --now ytkb
```

In questo caso configurazione e dati stanno nella cartella del progetto (`config/`, `.env`, `data/`).
