# AimiliVPN V2.1.9 正式版

- 首页显示当前连接、服务器本机代理和实际出口 IP。桌面和手机都能直接切换已通过检测的节点。点击节点名称可查看详情、收藏或复测。
- 列表筛选只改变当前视图。「管理 → 订阅范围」控制采集国家，「代理与路由」控制自动选线。版本信息、日志和帮助收进管理菜单。
- 新安装使用 IPQuery 免费 HTTPS 接口识别公网 IP，也支持 ipapi.is 的匿名响应格式。类型证据不足时按 ASN 查询 GitHub 上 ipverse 的网络分类，运营商接入网络显示为「疑似住宅 IP」。
- 入口地址和实际出口分别查询。资料在后台分批显示，遇到接口限流会退避。只有本机测出的延迟会标成实测值。

## 安装

```bash
curl -fsSL https://github.com/OpenMili/aimili-vpngate/releases/latest/download/install.sh -o aimili.sh && sudo bash aimili.sh
```

选择 **1 系统版** 或 **2 Docker 版**。安装器在登录页就绪后显示完整地址、账号和密码。Docker 版需要已有 Docker Engine 和 Compose 插件。

- 新面板绑定 `0.0.0.0`，从 `8787` 起自动选择空闲端口，并保存实际端口。云安全组可仅向你的管理 IP 开放该端口。公网长期使用可通过 HTTPS 反向代理访问。
- 本机 HTTP/SOCKS5 代理从 `127.0.0.1:7928` 起选择端口。安装器会识别同一台主机上通过另一种方式安装的 AimiliVPN。
- 升级沿用持久化的账号和监听配置。首次成功登录后，初始密码文件自动清除。
- 清空旧测试安装，在下载脚本的目录运行 `sudo bash aimili.sh --purge`。该操作删除 AimiliVPN 的系统服务、受管理的 Docker 容器和数据卷，以及对应的安装文件和账号数据。
