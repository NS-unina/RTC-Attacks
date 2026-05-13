# Usiamo la base ufficiale Linuxserver Webtop con Ubuntu XFCE
FROM lscr.io/linuxserver/webtop:ubuntu-xfce

ARG LINPHONE_APPIMAGE=Linphone-6.1.2-x86_64.AppImage
ARG LINPHONE_URL=https://download.linphone.org/releases/linux/app/${LINPHONE_APPIMAGE}

# Linphone Desktop is not available as an apt package in the current Webtop
# Ubuntu base, so install the official upstream AppImage instead.
RUN \
  echo "**** install linphone ****" && \
  apt-get update && \
  apt-get install -y \
    ca-certificates \
    curl \
    libxcb-cursor0 && \
  mkdir -p /opt/linphone && \
  curl -fL "${LINPHONE_URL}" -o /opt/linphone/Linphone.AppImage && \
  chmod +x /opt/linphone/Linphone.AppImage && \
  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'export APPIMAGE_EXTRACT_AND_RUN=1' \
    'exec /opt/linphone/Linphone.AppImage "$@"' \
    > /usr/local/bin/linphone && \
  chmod +x /usr/local/bin/linphone && \
  printf '%s\n' \
    '[Desktop Entry]' \
    'Type=Application' \
    'Name=Linphone' \
    'Comment=SIP softphone' \
    'Exec=/usr/local/bin/linphone' \
    'Terminal=false' \
    'Categories=Network;Telephony;' \
    > /usr/share/applications/linphone.desktop && \
  echo "**** cleanup ****" && \
  apt-get clean && \
  rm -rf /var/lib/apt/lists/*

# Esponiamo le porte necessarie
# 3000: KasmVNC (Interfaccia Browser)
# 5060: SIP
# 10000-10100: RTP Audio
EXPOSE 3000 5060/udp 10000-10100/udp
