FROM debian:bookworm-slim

ARG TARGETARCH
ARG TARGETVARIANT
ARG BUILD_VERSION=dev

LABEL org.opencontainers.image.title="AimiliVPN" \
      org.opencontainers.image.description="VPNGate node manager with HTTP and SOCKS5 proxy" \
      org.opencontainers.image.source="https://github.com/baoweise-bot/aimili-vpngate" \
      org.opencontainers.image.version="${BUILD_VERSION}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        iproute2 \
        iptables \
        openvpn \
        procps \
        psmisc \
        python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY VERSION README.md LICENSE ./
COPY vpngate_manager.py vpn_utils.py proxy_server.py snapshot_utils.py manual_target.py proxyctl.py official_web.py ./
COPY mirror ./mirror

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEPLOYMENT_MODE=docker \
    VPNGATE_DATA_DIR=/data \
    UI_HOST=127.0.0.1 \
    UI_PORT=8787 \
    LOCAL_PROXY_HOST=127.0.0.1 \
    LOCAL_PROXY_PORT=7928

RUN mkdir -p /data \
    && python3 -m py_compile vpngate_manager.py vpn_utils.py proxy_server.py snapshot_utils.py manual_target.py proxyctl.py official_web.py

VOLUME ["/data"]
EXPOSE 8787/tcp 7928/tcp
STOPSIGNAL SIGTERM

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python3 -c "import os,socket; s=socket.create_connection(('127.0.0.1',int(os.environ.get('UI_PORT','8787'))),3); s.close()"

CMD ["python3", "vpngate_manager.py"]
