<div align="center">

# AimiliVPN

**A VPNGate node manager and HTTP / HTTPS / SOCKS5 proxy gateway for Linux VPS hosts**

[![Release](https://img.shields.io/github/v/release/baoweise-bot/aimili-vpngate?style=flat-square&label=stable&color=16a34a)](https://github.com/baoweise-bot/aimili-vpngate/releases/latest)
[![Docker](https://img.shields.io/badge/Docker-amd64%20%7C%20386%20%7C%20arm64%20%7C%20armv7-0ea5e9?style=flat-square&logo=docker&logoColor=white)](https://github.com/baoweise-bot/aimili-vpngate/pkgs/container/aimili-vpngate)
[![License](https://img.shields.io/badge/License-GPL--3.0-334155?style=flat-square)](../LICENSE)

[简体中文](../README.md) · **English** · [日本語](README.ja.md) · [한국어](README.ko.md)

[Quick install](#quick-install) · [Installation](#installation) · [Connection](#connection) · [Recommended services](#vps) · [Community](#community) · [Legal notice](#legal)

[![Website](https://img.shields.io/badge/Website-339936.xyz-f97316?style=for-the-badge)](https://339936.xyz)
[![Telegram](https://img.shields.io/badge/Telegram-Community-229ED9?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/arestemple)
[![YouTube](https://img.shields.io/badge/YouTube-Tutorial-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](https://www.youtube.com/watch?v=s-ATfXR8BpI)

</div>

AimiliVPN uses Python's standard library to manage VPNGate nodes. It provides node discovery and testing, connection switching, a Web dashboard, and HTTP, HTTPS website proxying, and SOCKS5 access on one local port.

| Item | Default or supported range |
| --- | --- |
| Web dashboard | TCP `8787`, a private path, username, and password |
| Local proxy | `127.0.0.1:7928`, HTTP, HTTPS `CONNECT`, and SOCKS5 |
| Source deployment | x64, x86, ARM64, and ARM32 Linux |
| Docker images | `linux/amd64`, `linux/386`, `linux/arm64`, and `linux/arm/v7` |
| Update channel | GitHub `main` stable branch / latest stable Release |

> [!IMPORTANT]
> **Network availability:** Some regions, data centers, and network providers may restrict DNS, VPNGate APIs, GitHub mirrors, or VPN protocols. Mirrors and local snapshots improve node-list availability but cannot guarantee a successful connection on every host. Confirm that local law and your VPS provider permit VPN/TUN before deployment.

<a id="quick-install"></a>
## Quick Install

Run as `root` on a supported Linux VPS:

```bash
bash <(curl -Ls https://raw.githubusercontent.com/baoweise-bot/aimili-vpngate/main/install.sh)
```

The installer prints the complete Web URL, private path, username, and password. Run `ml` to open the management menu.

> [!TIP]
> Enable TUN/TAP in the VPS control panel and verify that `/dev/net/tun` exists. The Web dashboard uses TCP `8787` by default; restrict firewall access to your own IP whenever possible.

<a id="vps"></a>
## Recommended Services

| Provider | Type | Why we recommend it | Link |
| --- | --- | --- | --- |
| **BandwagonHost** | VPS | Optimized China Telecom CN2 GIA, China Unicom 9929, and China Mobile CMIN2 routes; low latency and strong stability for TikTok Live, cross-border commerce, and long-running global services. | [View offer](https://bandwagonhost.com/aff.php?aff=81790) |
| **RackNerd** | VPS | 4000GB of monthly traffic with strong value for the price; low deployment costs for services that need to run continuously. | [View offer](https://my.racknerd.com/aff.php?aff=18708) |
| **OpenMili** | AI relay | Direct GPT model access without model substitution, a low-cost 1:2 rate, and image generation support. | [Visit OpenMili](https://openmili.com/) |

Some links are affiliate links. Using them does not increase your price.

Before purchasing, confirm that the selected plan permits TUN/TAP, OpenVPN, and the required network protocols. An affiliate link is not a guarantee that a specific plan will work.

<a id="installation"></a>
## Installation

### Requirements

- Ubuntu, Debian, Alpine, CentOS, RHEL, Rocky Linux, AlmaLinux, Fedora, Oracle Linux, or Amazon Linux.
- `root`, OpenVPN, iptables, policy routing, and TUN/TAP.
- Windows and macOS can be proxy clients, but cannot run the full gateway. Docker Desktop is not equivalent to a Linux VPS with host TUN access.

### Option 1: Source installer

```bash
bash <(curl -Ls https://raw.githubusercontent.com/baoweise-bot/aimili-vpngate/main/install.sh)
```

The installer deploys to `/opt/aimilivpn` and registers a system service.

For unattended installation, explicitly skip the first-run prompts and generate the Web path and credentials automatically:

```bash
AIMILIVPN_NONINTERACTIVE=1 bash <(curl -Ls https://raw.githubusercontent.com/baoweise-bot/aimili-vpngate/main/install.sh)
```

```bash
ml                 # Open the management menu
ml status          # Show status, Web URL, and username
ml logs            # Follow logs
ml restart         # Restart the service
ml password        # Reset Web credentials
ml update          # Update from the stable main branch
ml uninstall       # Uninstall
```

To inspect the installer first:

```bash
git clone --branch main --single-branch https://github.com/baoweise-bot/aimili-vpngate.git
cd aimili-vpngate
sudo bash install.sh
```

Universal Linux source archives and SHA-256 checksums are available from [GitHub Releases](https://github.com/baoweise-bot/aimili-vpngate/releases/latest). Version changes are documented in the Release Notes.

### Option 2: Docker Compose

The Docker host must provide `/dev/net/tun`, host networking, `NET_ADMIN`, and `NET_RAW`.

```bash
git clone --branch main --single-branch https://github.com/baoweise-bot/aimili-vpngate.git
cd aimili-vpngate
docker compose pull
docker compose up -d
docker logs -f aimilivpn
```

Image: `ghcr.io/baoweise-bot/aimili-vpngate:2.1`

Update:

```bash
docker compose pull
docker compose up -d
```

<details>
<summary><strong>Show the docker run command</strong></summary>

```bash
docker run -d \
  --name aimilivpn \
  --restart unless-stopped \
  --network host \
  --cap-add NET_ADMIN \
  --cap-add NET_RAW \
  --device /dev/net/tun:/dev/net/tun \
  -e UI_HOST=0.0.0.0 \
  -e UI_PORT=8787 \
  -e LOCAL_PROXY_HOST=127.0.0.1 \
  -e LOCAL_PROXY_PORT=7928 \
  -v aimilivpn-data:/data \
  ghcr.io/baoweise-bot/aimili-vpngate:2.1
```

</details>

<details>
<summary><strong>Build locally when GHCR is unavailable</strong></summary>

```bash
git clone --branch main --single-branch https://github.com/baoweise-bot/aimili-vpngate.git
cd aimili-vpngate
docker compose build
docker compose up -d
```

</details>

<a id="connection"></a>
## Connection and Use

### 1. Sign in to the Web dashboard

For a source installation, open the URL printed by the installer:

```text
http://VPS_IP:8787/private_path/
```

Run `ml status` to recover the URL, or `ml password` to reset credentials.

Docker users can read the initial Web configuration with:

```bash
docker exec aimilivpn cat /data/ui_auth.json
```

Use its `secret_path`, `username`, and `password`, then change them after the first sign-in.

### 2. Fetch and connect to a node

1. Sign in and wait for the first node list, or select **Update nodes**.
2. Filter by country and use **Test** to measure reachability and latency from the VPS.
3. Select **Switch** on the target node. A failed target precheck should leave the current usable connection in place when possible.
4. Choose Smart Auto, Fixed Country, or Fixed IP routing.
5. Confirm the VPN state and outbound IP in the status area.

> [!NOTE]
> **Automatic Russia node filtering:** after a successful probe, the node's physical location is resolved from its IP; a node located in Russia is automatically marked unavailable and excluded from Smart Auto, fast-connect, and periodic checks. Its location is still shown in the node list for transparency.

### 3. Use the proxy on the VPS

HTTP, HTTPS website proxying, and SOCKS5 share `127.0.0.1:7928`. HTTPS sites use the HTTP proxy's `CONNECT` method, so the proxy URL remains `http://127.0.0.1:7928`.

```bash
# HTTP / HTTPS
curl -x http://127.0.0.1:7928 https://api.ipify.org

# SOCKS5 with remote DNS resolution
curl --proxy socks5h://127.0.0.1:7928 https://api.ipify.org
```

### 4. Connect from another computer

The proxy listens on the VPS loopback address by default. Use an SSH tunnel instead of exposing it publicly:

```bash
ssh -N \
  -L 8787:127.0.0.1:8787 \
  -L 7928:127.0.0.1:7928 \
  root@VPS_IP
```

After the tunnel is established:

- Web: `http://127.0.0.1:8787/private_path/`
- HTTP / HTTPS proxy: `127.0.0.1:7928`
- SOCKS5 proxy: `127.0.0.1:7928`; enable remote DNS or `socks5h` when available

> [!WARNING]
> Port `7928` has no public-facing user authentication by default. Never expose it directly without a firewall, source-IP restriction, or another reliable access-control layer.

<a id="community"></a>
## Website, Community, and Video

| Destination | Purpose | Link |
| --- | --- | --- |
| Website / forum | Announcements and discussion | [339936.xyz](https://339936.xyz) |
| Telegram group | Real-time community chat | [t.me/arestemple](https://t.me/arestemple) |
| YouTube tutorial | Installation and usage video | [Watch](https://www.youtube.com/watch?v=s-ATfXR8BpI) |
| GitHub Issues | Reproducible bugs and feature requests | [Open an issue](https://github.com/baoweise-bot/aimili-vpngate/issues) |
| Email | Bug reports and contact | [yaohunse7@gmail.com](mailto:yaohunse7@gmail.com) |

<a id="legal"></a>
## Scope of Use and Legal Notice

> [!CAUTION]
> By downloading, deploying, or using this project, you are responsible for confirming compliance with the laws of your location, the laws where the VPS is hosted, provider terms, and applicable VPNGate rules. This section defines project boundaries, is not legal advice, and cannot guarantee exemption from any liability imposed by law.

1. **Permitted purpose:** Use only for lawful network research, education, development testing, privacy protection, and authorized access. Do not use it to evade lawfully imposed controls, gain unauthorized access, attack or scan systems, send spam, commit fraud, infringe rights, or conduct any unlawful activity.
2. **Network and regional restrictions:** Some regions and data centers may restrict VPNGate, GitHub mirrors, or remote VPN nodes. The project does not guarantee continuous availability in any region or on any host. Use it only where local law and provider terms permit.
3. **Third-party nodes:** VPNGate nodes are operated by third-party volunteers. This project does not own, control, or audit them and cannot guarantee availability, speed, security, privacy practices, or logging behavior. Do not send passwords, financial information, trade secrets, or other sensitive data through untrusted nodes.
4. **User responsibility:** The user is responsible for node selection, traffic, deployment location, exposed ports, and account security, and bears legal responsibility for unlawful use, misconfiguration, third-party nodes, outages, data leaks, or account abuse.
5. **No warranty:** The software is provided “as is.” To the maximum extent permitted by applicable law, maintainers disclaim warranties of availability, merchantability, fitness for a particular purpose, and indirect damages. Liability that cannot lawfully be excluded remains unaffected.
6. **Stop if uncertain:** If you cannot confirm that local law and provider policy permit this use, do not deploy or use the software and consult a qualified lawyer in the relevant jurisdiction.

<div align="center">

[Stable Release](https://github.com/baoweise-bot/aimili-vpngate/releases/latest) · [Issues](https://github.com/baoweise-bot/aimili-vpngate/issues) · [GPL-3.0 License](../LICENSE)

</div>
