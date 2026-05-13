#!/bin/sh
set -eu

CONF_DIR=${CONF_DIR:-/data}
CONF_PATH=${CONF_PATH:-$CONF_DIR/linphonerc}
FIFO_PATH=${FIFO_PATH:-/tmp/linphonec.fifo}
LOG_PATH=${LOG_PATH:-/var/log/linphonec.log}
SIP_DOMAIN=${SIP_DOMAIN:-10.10.0.5}
SIP_PROXY=${SIP_PROXY:-10.10.0.5}
SIP_USERNAME=${SIP_USERNAME:?missing SIP_USERNAME}
SIP_PASSWORD=${SIP_PASSWORD:?missing SIP_PASSWORD}
SIP_REALM=${SIP_REALM:-$SIP_DOMAIN}
AUTOANSWER=${AUTOANSWER:-false}
USE_FILE_AUDIO=${USE_FILE_AUDIO:-true}
CLI_AUDIO_FILE=${CLI_AUDIO_FILE:-}

mkdir -p "$CONF_DIR" /var/log /root/.local/share/linphone

cat >"$CONF_PATH" <<EOF
[sip]
default_proxy=0
media_encryption=none
register_only_when_network_is_up=0
sip_port=-1

[proxy_0]
reg_proxy=sip:${SIP_PROXY};transport=udp
reg_identity=sip:${SIP_USERNAME}@${SIP_DOMAIN}
reg_expires=3600
reg_sendregister=1
publish=0
avpf=0
quality_reporting_enabled=0
quality_reporting_interval=0

[auth_info_0]
username=${SIP_USERNAME}
passwd=${SIP_PASSWORD}
realm=${SIP_REALM}
domain=${SIP_DOMAIN}
algorithm=MD5
EOF

rm -f "$FIFO_PATH"
mkfifo "$FIFO_PATH"
: >"$LOG_PATH"

if [ "$AUTOANSWER" = "true" ]; then
  set -- linphonec -S -a -c "$CONF_PATH"
else
  set -- linphonec -S -c "$CONF_PATH"
fi

(sh -c 'while true; do cat "$1"; done' sh "$FIFO_PATH" | "$@" >"$LOG_PATH" 2>&1) &

sleep 3

if [ "$USE_FILE_AUDIO" = "true" ]; then
  printf 'soundcard use files\n' >"$FIFO_PATH"
fi

if [ -n "$CLI_AUDIO_FILE" ] && [ -f "$CLI_AUDIO_FILE" ]; then
  printf 'play %s\n' "$CLI_AUDIO_FILE" >"$FIFO_PATH"
fi

tail -f "$LOG_PATH"
