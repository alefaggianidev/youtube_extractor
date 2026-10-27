#!/bin/sh
# Avvio del container ytkb:
#  1. aggiorna yt-dlp (YouTube cambia spesso: una versione vecchia smette di funzionare);
#  2. al primo avvio crea config/ e .env in $YTKB_HOME dai file di esempio;
#  3. esegue il comando richiesto (default: "run", il demone).
set -eu

if [ "${YTKB_UPDATE_YTDLP:-1}" = "1" ]; then
    echo "ytkb: aggiorno yt-dlp..." >&2
    if ! uv pip install --quiet --python /opt/venv/bin/python --upgrade "yt-dlp[default]"; then
        echo "ytkb: aggiornamento di yt-dlp non riuscito, continuo con la versione installata" >&2
    fi
fi

if [ "${1:-}" != "init" ] && [ ! -f "${YTKB_HOME}/config/settings.yaml" ]; then
    echo "ytkb: primo avvio, creo la configurazione in ${YTKB_HOME}" >&2
    ytkb init
fi

exec ytkb "$@"
