FROM python:3.12-slim

# AimiliVPN only uses the Python standard library (zero pip deps),
# but it shells out to openvpn / iptables / iproute2 / psmisc / sysctl
# at runtime, and needs /dev/net/tun + CAP_NET_ADMIN (granted via
# docker-compose.yml, not here) to create the TUN adapter.
RUN apt-get update && apt-get install -y --no-install-recommends \
      openvpn \
      iptables \
      iproute2 \
      psmisc \
      procps \
      ca-certificates \
      curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only the three runtime entry points. install.sh / ml / *.md are
# host-install helpers and not needed inside the container.
COPY proxy_server.py vpn_utils.py vpngate_manager.py ./

# Persistent runtime data (nodes.json, state, logs, auth, configs).
VOLUME ["/data"]

EXPOSE 8787 7928

CMD ["python3", "vpngate_manager.py"]