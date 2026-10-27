#!/bin/bash
# =============================================================================
#  Preparazione della VM RHEL 9 (da eseguire UNA volta come root):
#    sudo bash deploy/rhel9/prepare-root.sh
#  - installa Podman e git
#  - crea l'utente di servizio "ytkb" (senza privilegi) e la cartella dati /srv/ytkb
#  - abilita il "linger": i servizi dell'utente ytkb partono all'avvio della VM anche senza login
# =============================================================================
set -euo pipefail

SERVICE_USER="${SERVICE_USER:-ytkb}"
DATA_DIR="${DATA_DIR:-/srv/ytkb}"

if [[ $EUID -ne 0 ]]; then
    echo "Esegui come root (sudo)." >&2
    exit 1
fi

dnf install -y podman git

if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --create-home --shell /bin/bash "$SERVICE_USER"
    echo "Creato l'utente $SERVICE_USER"
fi

mkdir -p "$DATA_DIR"
chown "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR"
chmod 750 "$DATA_DIR"

loginctl enable-linger "$SERVICE_USER"

echo
echo "Fatto. Ora:"
echo "  1. copia il repository nella home di $SERVICE_USER (git clone o scp)"
echo "  2. sudo -iu $SERVICE_USER"
echo "  3. bash youtube_extractor/deploy/rhel9/install-user.sh"
