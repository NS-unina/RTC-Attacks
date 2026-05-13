#!/bin/sh
set -eu

CONF_DIR=${CONF_DIR:-/data}
FIFO_PATH=${FIFO_PATH:-/tmp/baresip.fifo}
LOG_PATH=${LOG_PATH:-/var/log/baresip.log}
SIP_DOMAIN=${SIP_DOMAIN:-10.10.0.5}
SIP_USERNAME=${SIP_USERNAME:?missing SIP_USERNAME}
SIP_PASSWORD=${SIP_PASSWORD:?missing SIP_PASSWORD}
AUTOANSWER=${AUTOANSWER:-false}
AUDIO_SOURCE_FILE=${AUDIO_SOURCE_FILE:-/media/audio_cli.wav}
SIP_TRANSPORT=${SIP_TRANSPORT:-udp}
SIP_PORT=${SIP_PORT:-5060}

mkdir -p "$CONF_DIR" /var/log

cat >"$CONF_DIR/config" <<EOF
poll_method epoll
sip_listen 0.0.0.0:${SIP_PORT}
audio_player aubridge,default
audio_source aufile,${AUDIO_SOURCE_FILE}
audio_alert aubridge,default
audio_buffer 20-160
rtp_stats yes
snd_path /captures
module_path /usr/lib/baresip/modules
module stdio.so
module g711.so
module aufile.so
module aubridge.so
module stun.so
module turn.so
module ice.so
module_app contact.so
module_app debug_cmd.so
module_app menu.so
module_tmp uuid.so
module_tmp account.so
module sndfile.so
EOF

ANSWERMODE=""
if [ "$AUTOANSWER" = "true" ]; then
  ANSWERMODE=";answermode=auto"
fi

cat >"$CONF_DIR/accounts" <<EOF
<sip:${SIP_USERNAME}@${SIP_DOMAIN};transport=${SIP_TRANSPORT}>;auth_user=${SIP_USERNAME};auth_pass=${SIP_PASSWORD}${ANSWERMODE};audio_codecs=PCMU/8000;audio_source=aufile,${AUDIO_SOURCE_FILE};audio_player=aubridge,default
EOF

rm -f "$FIFO_PATH"
mkfifo "$FIFO_PATH"
: >"$LOG_PATH"

(sh -c 'while true; do cat "$1"; done' sh "$FIFO_PATH" | baresip -f "$CONF_DIR" >"$LOG_PATH" 2>&1) &

tail -f "$LOG_PATH"
