# AimiliVPN V2.1.6 正式版

## 本版变更

- **节点获取。** 优先使用 VPN Gate 官方 HTTPS，失败后依次读取 GitHub Pages、本地缓存和内置快照。备用源会核对 CSV 与元数据的 SHA‑256，并提示快照是否超过 30 分钟。Compose 可配置 `OPENVPN_UPSTREAM_HTTP` 或 `OPENVPN_UPSTREAM_SOCKS`。默认目标是探测到 3 个可用节点。
- **Docker 与连接切换。** 补齐镜像中的 `curl` 和 `ping`。出口检查使用 HTTPS。统一手动与自动的住宅节点筛选，并修复切换期间阻塞状态读写及断开后就绪状态残留的问题。
- **OpenVPN 与代理。** 下载与启动阶段都校验 OpenVPN 配置，收紧节点的证书约束。代理 DNS 通过 VPN 隧道查询。修复 HTTP、SOCKS5 输入校验及 TCP 半关闭处理。服务退出时清理自身隧道和专用策略路由。
- **管理后台。** 新安装默认绑定 `127.0.0.1`，生成随机管理路径。密码保存为 PBKDF2 哈希。登录增加限流，改密后旧会话失效。远程管理可通过 SSH 端口转发。
- **安装与更新。** 源码安装使用已校验的发行包。新版 `ml update` 支持指定正式标签，并在执行安装器之前校验 SHA‑256。OpenRC 服务与日志轮转也已更新。

## 一键安装

在启用了 TUN/TAP 的 Linux VPS 上以 `root` 执行。选择其中一段命令。

**源码版**会校验发行包 SHA-256，安装系统服务并生成首次登录凭据。[下载 install-source.sh](https://github.com/OpenMili/aimili-vpngate/releases/download/v2.1.6/install-source.sh)

```bash
curl -fsSLO https://github.com/OpenMili/aimili-vpngate/releases/download/v2.1.6/install-source.sh && bash install-source.sh
```

**Docker 版**需已安装 Docker Engine 和 Compose 插件。配置保存在 `/opt/aimilivpn-docker`。已有其他方式部署的容器请用原部署配置升级。[下载 install-docker.sh](https://github.com/OpenMili/aimili-vpngate/releases/download/v2.1.6/install-docker.sh)

```bash
curl -fsSLO https://github.com/OpenMili/aimili-vpngate/releases/download/v2.1.6/install-docker.sh && bash install-docker.sh
```

## 手动安装或从旧版升级

把源码包和同一发行版的 `sha256sums.txt` 下载到一个新目录，在 Linux 上以 `root` 校验并安装。

```bash
sha256sum -c sha256sums.txt &&
  tar -xzf aimilivpn-v2.1.6-linux-source.tar.gz &&
  cd aimilivpn-v2.1.6-linux-source &&
  bash install.sh
```

从 `v2.1.5` 及更早的源码版升级时，请先执行上面的流程。升级保留现有管理配置。请核对已有 `ui_auth.json` 的 `host`，将仅供本机管理的实例设为 `127.0.0.1`。

Docker 镜像为 `ghcr.io/openmili/aimili-vpngate:2.1.6`，支持 `linux/amd64`、`linux/386`、`linux/arm64` 和 `linux/arm/v7`。使用本版 Compose 配置可执行 `docker compose pull && docker compose up -d`。旧版 Compose 用户应先核对镜像地址和管理监听地址，并沿用现有数据卷。全新容器的首次登录信息可用 `docker exec aimilivpn cat /data/ui_bootstrap.json` 获取。首次成功登录后该文件会清除。

## 兼容性与测试

- 发布前工作树已通过 61 项单元测试。Docker 在隔离环境完成 Web 登录、HTTP、HTTPS CONNECT、SOCKS5、手动切换、自动故障转移和退出清理。另有一个公网 VPN Gate 节点通过出口检查。
- Alpine/OpenRC 实测通过安装、校验更新、启停和卸载。Debian 验证了 systemd 单元和安装器报告启动失败的行为。Debian 实机的完整安装启动仍待验证。
- GitHub Pages 定时任务配置为每 15 分钟触发。实际发布时间以快照元数据为准，备用列表中的节点仍需连通性检测。
