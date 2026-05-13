FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Europe/Rome

RUN apt-get update && \
    apt-get install -y --no-install-recommends linphone-cli ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /usr/local/bin/linphone-cli-entrypoint.sh
COPY linphone-cli-send /usr/local/bin/linphone-cli-send

RUN chmod +x /usr/local/bin/linphone-cli-entrypoint.sh /usr/local/bin/linphone-cli-send

ENTRYPOINT ["/usr/local/bin/linphone-cli-entrypoint.sh"]
