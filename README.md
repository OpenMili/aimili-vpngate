<div align="center">

# AimiliVPN

**面向 Linux VPS 的 VPNGate 节点管理与 HTTP / HTTPS / SOCKS5 代理网关**

[![正式版本](https://img.shields.io/github/v/release/baoweise-bot/aimili-vpngate?style=flat-square&label=正式版&color=16a34a)](https://github.com/baoweise-bot/aimili-vpngate/releases/latest)
[![Docker](https://img.shields.io/badge/Docker-amd64%20%7C%20386%20%7C%20arm64%20%7C%20armv7-0ea5e9?style=flat-square&logo=docker&logoColor=white)](https://github.com/baoweise-bot/aimili-vpngate/pkgs/container/aimili-vpngate)
[![License](https://img.shields.io/badge/License-GPL--3.0-334155?style=flat-square)](LICENSE)

**简体中文** · [English](docs/README.en.md) · [日本語](docs/README.ja.md) · [한국어](docs/README.ko.md)

[快速安装](#quick-install) · [完整安装](#installation) · [连接使用](#connection) · [服务商推荐](#vps) · [社区入口](#community) · [法律声明](#legal)

[![项目网站](https://img.shields.io/badge/项目网站-339936.xyz-f97316?style=for-the-badge)](https://339936.xyz)
[![Telegram](https://img.shields.io/badge/Telegram-交流群-229ED9?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/arestemple)
[![YouTube](https://img.shields.io/badge/YouTube-视频教程-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](https://www.youtube.com/watch?v=s-ATfXR8BpI)

</div>

<a id="vps"></a>

## 服务商推荐

| 商家 | 推荐理由 | 入口 |
| --- | --- | --- |
| **Bandwagon** |代理 & 建站推荐：CN2/9929/CMI三网直连 2500 Mbps 高速线路；低延迟、高稳定性，适合直播、带货和长期出海业务。 | [立即查看](https://bandwagonhost.com/aff.php?aff=81790) |
| **RackNerd** | 综合服务器推荐：4000GB 大流量，价格与配置性价比突出；部署成本低，适合需要长期稳定运行的服务。 | [立即查看](https://my.racknerd.com/aff.php?aff=18708) |
| **OpenMili** | OpenMili Ai 中转站推荐：GPT-6 Astra & Images 2.0 Pro 美区原价 0.12倍率 不掺假、不降智，接受任何压力测试！| [立即查看](https://openmili.com/) |
| **JTTI VPS** | 稳定建站服务器推荐：5 Mbps 独享带宽 无限流量 CN2/9929/CMI三网直连，跨境网站访问低延迟，长期稳定API运营。| [立即查看](https://www.jtti.cc/zh/activity/y2026-national-day.html?k=baoweise) |

AimiliVPN 使用 Python 标准库管理 VPNGate 节点，提供节点获取与检测、连接切换、Web 管理后台，以及共用一个端口的 HTTP、HTTPS 网站代理和 SOCKS5 代理服务。

| 项目 | 默认值或支持范围 |
| --- | --- |
| Web 管理后台 | TCP `8787` + 独立安全路径 + 账号密码 |
| 本机代理 | `127.0.0.1:7928`，支持 HTTP、HTTPS `CONNECT` 和 SOCKS5 |
| 源码部署 | x64、x86、ARM64、ARM32 Linux |
| Docker 镜像 | `linux/amd64`、`linux/386`、`linux/arm64`、`linux/arm/v7` |
| 更新通道 | GitHub `main` 正式分支 / 最新正式 Release |

> [!IMPORTANT]
> **网络可用性提示：** 不同地区、数据中心和网络服务商可能限制 DNS、VPNGate API、GitHub 镜像或 VPN 协议。镜像与本地缓存只能提高节点列表的可用性，不能保证所有机型都能建立连接。部署前请确认所在地法律和 VPS 服务商条款允许使用 VPN/TUN。

<a id="quick-install"></a>
## 快速安装

使用 `root` 用户在受支持的 Linux VPS 上执行：

```bash
bash <(curl -Ls https://raw.githubusercontent.com/baoweise-bot/aimili-vpngate/main/install.sh)
```

安装完成后，终端会显示 Web 后台完整地址、随机安全路径、登录账号和密码。输入 `ml` 可打开管理菜单。

无人值守安装可显式跳过首次参数询问，并自动生成安全路径和登录凭据：

```bash
AIMILIVPN_NONINTERACTIVE=1 bash <(curl -Ls https://raw.githubusercontent.com/baoweise-bot/aimili-vpngate/main/install.sh)
```

> [!TIP]
> 安装前请在 VPS 控制面板启用 TUN/TAP，并确认 `/dev/net/tun` 存在。Web 默认使用 TCP `8787`，安全组建议只允许自己的 IP 访问。

<a id="installation"></a>
## 完整安装

### 运行条件

- 操作系统：Ubuntu、Debian、Alpine、CentOS、RHEL、Rocky Linux、AlmaLinux、Fedora、Oracle Linux 或 Amazon Linux。
- 权限与组件：`root`、OpenVPN、iptables、策略路由和 TUN/TAP。
- Windows 与 macOS 可作为代理客户端，但不能直接运行完整网关；Docker Desktop 也不等同于具备宿主机 TUN 能力的 Linux VPS。

### 方式一：一键源码安装

```bash
bash <(curl -Ls https://raw.githubusercontent.com/baoweise-bot/aimili-vpngate/main/install.sh)
```

安装器会部署到 `/opt/aimilivpn` 并注册系统服务。常用命令：

```bash
ml                 # 打开管理菜单
ml status          # 查看状态、Web 地址和账号
ml logs            # 查看实时日志
ml restart         # 重启服务
ml password        # 重设 Web 账号密码
ml update          # 从 main 正式分支更新
ml uninstall       # 卸载
```

需要先审查脚本时：

```bash
git clone --branch main --single-branch https://github.com/baoweise-bot/aimili-vpngate.git
cd aimili-vpngate
sudo bash install.sh
```

通用 Linux 源码包与 SHA-256 校验文件可在 [GitHub Releases](https://github.com/baoweise-bot/aimili-vpngate/releases/latest) 下载，版本变更记录也统一放在 Release Notes 中。

### 方式二：Docker Compose

Docker 主机需要 `/dev/net/tun`、host 网络以及 `NET_ADMIN`、`NET_RAW` 权限。

```bash
git clone --branch main --single-branch https://github.com/baoweise-bot/aimili-vpngate.git
cd aimili-vpngate
docker compose pull
docker compose up -d
docker logs -f aimilivpn
```

正式镜像：`ghcr.io/baoweise-bot/aimili-vpngate:2.1`

更新容器：

```bash
docker compose pull
docker compose up -d
```

<details>
<summary><strong>查看 docker run 命令</strong></summary>

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
<summary><strong>无法拉取 GHCR 时在 VPS 本地构建</strong></summary>

```bash
git clone --branch main --single-branch https://github.com/baoweise-bot/aimili-vpngate.git
cd aimili-vpngate
docker compose build
docker compose up -d
```

</details>

<a id="connection"></a>
## 连接与使用

### 1. 登录 Web 后台

源码安装完成后，使用终端输出的地址访问：

```text
http://VPS_IP:8787/随机安全路径/
```

忘记地址时执行 `ml status`；需要重设账号密码时执行 `ml password`。

Docker 用户可以读取首次启动时保存的 Web 配置：

```bash
docker exec aimilivpn cat /data/ui_auth.json
```

使用其中的 `secret_path`、`username` 和 `password` 登录，并在首次登录后修改安全路径和凭据。

### 2. 获取并连接节点

1. 登录后台，等待首次节点加载完成，或点击“更新节点”。
2. 按国家筛选节点，并使用“测试”检查本机实测延迟与可用性。
3. 点击目标节点的“切换”；目标预检失败时，程序会尽量保留当前可用连接。
4. 根据需要选择智能自动、固定国家或固定 IP 模式。
5. 在状态区域确认 VPN 已连接，并核对当前出口 IP。

### 3. 在 VPS 本机使用代理

HTTP、HTTPS 网站代理和 SOCKS5 共用 `127.0.0.1:7928`。HTTPS 网站通过 HTTP 代理的 `CONNECT` 方法访问，代理地址仍填写 `http://127.0.0.1:7928`。

```bash
# HTTP / HTTPS
curl -x http://127.0.0.1:7928 https://api.ipify.org

# SOCKS5，并通过代理解析域名
curl --proxy socks5h://127.0.0.1:7928 https://api.ipify.org
```

<details>
<summary><strong>查看 Shell 环境变量与 Python 示例</strong></summary>

```bash
export http_proxy="http://127.0.0.1:7928"
export https_proxy="http://127.0.0.1:7928"
curl https://api.ipify.org
```

```python
import requests

proxies = {
    "http": "http://127.0.0.1:7928",
    "https": "http://127.0.0.1:7928",
}

response = requests.get("https://api.ipify.org", proxies=proxies, timeout=20)
print(response.text)
```

</details>

### 4. 从电脑或其他设备连接

代理默认只监听 VPS 回环地址。推荐使用 SSH 隧道，不要直接暴露代理端口：

```bash
ssh -N \
  -L 8787:127.0.0.1:8787 \
  -L 7928:127.0.0.1:7928 \
  root@VPS_IP
```

隧道建立后：

- Web：`http://127.0.0.1:8787/随机安全路径/`
- HTTP / HTTPS 代理：`127.0.0.1:7928`
- SOCKS5 代理：`127.0.0.1:7928`，支持时选择远程 DNS 或 `socks5h`

> [!WARNING]
> `7928` 默认没有面向公网的用户认证。请勿在没有防火墙、来源 IP 限制或其他可靠访问控制的情况下将其直接开放到公网。

<a id="community"></a>
## 网站、社群与视频

| 入口 | 用途 | 链接 |
| --- | --- | --- |
| 项目网站 / 交流论坛 | 公告、经验交流与讨论 | [339936.xyz](https://339936.xyz) |
| Telegram 群 | 即时交流 | [t.me/arestemple](https://t.me/arestemple) |
| YouTube 教程 | 安装和使用视频 | [观看视频](https://www.youtube.com/watch?v=s-ATfXR8BpI) |
| GitHub Issues | 可复现的问题与功能建议 | [提交 Issue](https://github.com/baoweise-bot/aimili-vpngate/issues) |

<a id="legal"></a>
## 使用范围与法律声明

> [!CAUTION]
> 下载、部署或使用本项目即表示您应自行确认用途符合所在地法律、VPS 所在地法律、网络服务商条款及 VPNGate 的相关规则。以下内容是项目使用边界，不构成法律意见，也不能保证免除任何个人或组织依法应承担的责任。

1. **限定用途**：本项目仅用于合法的网络研究、教育、开发测试、隐私保护和经授权的网络访问，不得用于绕过依法实施的监管措施、未授权访问、攻击、扫描、垃圾信息、欺诈、侵权或其他违法活动。
2. **网络与地区限制**：不同地区和数据中心可能限制 VPNGate、GitHub 镜像或远端 VPN 节点。本项目不承诺任何地区或机型始终可用；仅应在当地法律和服务商条款允许的环境中合理使用。
3. **第三方节点**：VPNGate 节点由第三方志愿者运营，本项目不拥有、不控制也不审核这些节点，无法保证其稳定性、速度、安全性、隐私政策或日志行为。请勿通过不可信节点传输账号密码、金融信息、商业机密等敏感数据。
4. **用户责任**：节点选择、流量内容、部署位置、端口开放和账号安全均由使用者负责。因违法使用、配置不当、第三方节点、服务中断、数据泄露或账号滥用产生的后果，由使用者依法承担。
5. **无保证提供**：软件按“现状”提供，在适用法律允许的最大范围内，维护者不对可用性、适销性、特定用途适用性或间接损失作出保证。无法依法排除的责任不受本声明影响。
6. **不确定时停止使用**：如无法确认当地法律或服务商是否允许，请停止部署和使用，并咨询当地有执业资格的法律专业人士。

<div align="center">

[正式版本](https://github.com/baoweise-bot/aimili-vpngate/releases/latest) · [问题反馈](https://github.com/baoweise-bot/aimili-vpngate/issues) · [GPL-3.0 License](LICENSE)

</div>
