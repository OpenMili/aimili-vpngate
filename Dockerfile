FROM debian:bookworm-slim@sha256:e67eeead736ff7bbe258ef088bff683635c561b1fcfefad0806c1df4ab49ce0e

ARG TARGETARCH
ARG TARGETVARIANT
ARG BUILD_VERSION=dev

LABEL org.opencontainers.image.title="AimiliVPN" \
      org.opencontainers.image.description="VPNGate node manager with HTTP and SOCKS5 proxy" \
      org.opencontainers.image.source="https://github.com/OpenMili/aimili-vpngate" \
      org.opencontainers.image.version="${BUILD_VERSION}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        iproute2 \
        iputils-ping \
        iptables \
        openvpn \
        procps \
        psmisc \
        python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY VERSION README.md LICENSE ./
COPY vpngate_manager.py vpn_utils.py proxy_server.py snapshot_utils.py auth_store.py panel_access.py ./
COPY mirror ./mirror

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEPLOYMENT_MODE=docker \
    VPNGATE_DATA_DIR=/data \
    UI_HOST=0.0.0.0 \
    UI_PORT=8787 \
    LOCAL_PROXY_HOST=127.0.0.1 \
    LOCAL_PROXY_PORT=7928

RUN mkdir -p /data \
    && python3 -m py_compile vpngate_manager.py vpn_utils.py proxy_server.py snapshot_utils.py auth_store.py panel_access.py

VOLUME ["/data"]
EXPOSE 8787/tcp 7928/tcp
STOPSIGNAL SIGTERM

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python3", "/app/panel_access.py", "health"]

CMD ["python3", "vpngate_manager.py"]
