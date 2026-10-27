#!/bin/bash
# =============================================================================
#  Installazione/aggiornamento di ytkb come servizio (da eseguire come utente "ytkb", NON root):
#    bash deploy/rhel9/install-user.sh            # senza provider di PO token
#    WITH_POT=1 bash deploy/rhel9/install-user.sh # con il provider di PO token (opzionale)
#  Si può rilanciare dopo ogni `git pull`: ricostruisce l'immagine e riavvia il servizio.
# =============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WITH_POT="${WITH_POT:-0}"
QUADLET_DIR="$HOME/.config/containers/systemd"
UNIT_DIR="$HOME/.config/systemd/user"
DATA_DIR="${DATA_DIR:-/srv/ytkb}"

if [[ $EUID -eq 0 ]]; then
    echo "Non eseguire come root: usa l'utente di servizio (es. sudo -iu ytkb)." >&2
    exit 1
fi
if [[ ! -w "$DATA_DIR" ]]; then
    echo "La cartella $DATA_DIR non esiste o non è scrivibile: esegui prima deploy/rhel9/prepare-root.sh" >&2
    exit 1
fi

# systemctl --user ha bisogno di queste variabili quando si entra con sudo -iu
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

echo "==> Costruisco l'immagine (WITH_POT=$WITH_POT)"
podman build --build-arg "WITH_POT=$WITH_POT" -t localhost/ytkb:latest -f "$REPO_DIR/deploy/Containerfile" "$REPO_DIR"

echo "==> Installo le unità systemd (Quadlet)"
mkdir -p "$QUADLET_DIR" "$UNIT_DIR"
cp "$REPO_DIR/deploy/quadlet/ytkb.network" "$REPO_DIR/deploy/quadlet/ytkb.container" "$QUADLET_DIR/"
if [[ "$WITH_POT" == "1" ]]; then
    cp "$REPO_DIR/deploy/quadlet/bgutil-pot.container" "$QUADLET_DIR/"
fi
cp "$REPO_DIR/deploy/quadlet/ytkb-update.service" "$REPO_DIR/deploy/quadlet/ytkb-update.timer" "$UNIT_DIR/"

systemctl --user daemon-reload

if [[ ! -f "$DATA_DIR/config/settings.yaml" ]]; then
    echo "==> Primo avvio: creo la configurazione in $DATA_DIR"
    podman run --rm --userns=keep-id:uid=1000,gid=1000 -e YTKB_UPDATE_YTDLP=0 \
        -v "$DATA_DIR:/srv/ytkb:Z" localhost/ytkb:latest init
    echo
    echo "Configura ora i segreti e le impostazioni, poi rilancia questo script:"
    echo "   nano $DATA_DIR/.env                    # GEMINI_API_KEY (obbligatoria), TELEGRAM_BOT_TOKEN..."
    echo "   nano $DATA_DIR/config/settings.yaml"
    echo "   nano $DATA_DIR/config/channels.yaml    # oppure: ytkb channels import-takeout (vedi guida)"
    exit 0
fi

echo "==> Avvio dei servizi"
if [[ "$WITH_POT" == "1" ]]; then
    systemctl --user restart bgutil-pot.service
fi
systemctl --user restart ytkb.service
systemctl --user enable --now ytkb-update.timer

echo
echo "Fatto. Comandi utili:"
echo "   journalctl --user -u ytkb -f                 # log in tempo reale"
echo "   podman exec ytkb ytkb status                 # stato della coda"
echo "   podman exec ytkb ytkb doctor                 # diagnosi"
echo "   podman exec ytkb ytkb add --now <link>       # analizza subito un video"
