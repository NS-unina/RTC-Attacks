#!/bin/sh
set -eu

template=/etc/asterisk/sip.conf.template
target=/etc/asterisk/sip.conf

if [ -f "$template" ]; then
  sed \
    -e "s|__EXTERNAL_IP__|${EXTERNAL_IP:-}|g" \
    -e "s|__LOCAL_NET__|${LOCAL_NET:-}|g" \
    "$template" > "$target"
fi

exec "$@"
