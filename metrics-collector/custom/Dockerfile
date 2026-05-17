FROM python:3.11-slim

ENV POETRY_VERSION=1.8.3 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    PYTHONUNBUFFERED=1

# Previous implementation:
# RUN apt-get update \
#     && apt-get install -y --no-install-recommends curl make iputils-ping \
#     && rm -rf /var/lib/apt/lists/*
#
# Updated implementation:
# Install Docker CLI and docker-compose so stack Makefiles can invoke `docker`,
# `docker compose`, or `docker-compose` while using host daemon via mounted socket.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl make iputils-ping docker.io docker-compose \
    && rm -rf /var/lib/apt/lists/*

# Previous implementation:
# Relied on distro packages for `docker`, but in this base image that does not
# expose a usable docker CLI binary in PATH.
#
# Updated implementation:
# Install Docker CLI from the official static distribution so Makefiles that
# call `docker inspect/exec/logs/stats` work against the mounted host socket.
RUN set -eux; \
    ARCH="$(dpkg --print-architecture)"; \
    case "${ARCH}" in \
      amd64) DOCKER_ARCH="x86_64" ;; \
      arm64) DOCKER_ARCH="aarch64" ;; \
      *) echo "Unsupported architecture: ${ARCH}" >&2; exit 1 ;; \
    esac; \
    DOCKER_VERSION="27.5.1"; \
    curl -fsSL "https://download.docker.com/linux/static/stable/${DOCKER_ARCH}/docker-${DOCKER_VERSION}.tgz" -o /tmp/docker.tgz; \
    tar -xzf /tmp/docker.tgz -C /tmp; \
    mv /tmp/docker/docker /usr/local/bin/docker; \
    chmod +x /usr/local/bin/docker; \
    rm -rf /tmp/docker /tmp/docker.tgz

RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src

RUN poetry install --only main

ENTRYPOINT ["metrics-collector"]
CMD ["--help"]
