# Suricata IDS for RTC-Attacks project
# Change rationale: Suricata is more tolerant of invalid checksums (kernel offload)
# and better suited for offline PCAP analysis compared to Snort 3.

FROM jasonish/suricata:8.0.4

# Install additional utilities for capture and event monitoring
# Note: jasonish/suricata uses AlmaLinux (RHEL-based)
RUN dnf install -y \
        tcpdump \
        iproute \
        jq \
        wget \
    && dnf clean all

# Install Docker CLI binary (static binary to avoid repo complexity)
RUN wget -qO /tmp/docker.tgz https://download.docker.com/linux/static/stable/x86_64/docker-24.0.7.tgz && \
    tar -xzf /tmp/docker.tgz -C /tmp && \
    mv /tmp/docker/docker /usr/local/bin/docker && \
    chmod +x /usr/local/bin/docker && \
    rm -rf /tmp/docker /tmp/docker.tgz

# Set working directory
WORKDIR /var/log/suricata

# Default command: run in background mode
CMD ["suricata", "-c", "/etc/suricata/suricata.yaml", "-i", "any"]
