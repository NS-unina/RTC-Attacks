FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Europe/Rome

RUN apt-get update && \
    apt-get install -y --no-install-recommends baresip-core ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /usr/local/bin/baresip-cli-entrypoint.sh
COPY baresip-cli-send /usr/local/bin/baresip-cli-send

RUN chmod +x /usr/local/bin/baresip-cli-entrypoint.sh /usr/local/bin/baresip-cli-send

ENTRYPOINT ["/usr/local/bin/baresip-cli-entrypoint.sh"]
