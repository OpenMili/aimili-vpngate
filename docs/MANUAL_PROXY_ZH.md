# 按 IP / 国家手动切换代理出口

通过 Web 表单、`POST /api/select_target` 或 `proxyctl.py` 选择出口。HTTP CONNECT 与 SOCKS5 共用一个代理端口，一个实例同一时刻只有一个出口。

## 已实现的行为

- **按 IP**：从已有节点列表找到入口 IP，切换成功后保存 `fixed_ip` 与具体节点 ID；该节点失败时不会自动漂移到其他节点。同一 IP 有多个协议/端口时返回候选列表，必须进一步选择。
- **按国家**：使用两位国家代码，可多选，例如同时勾选美国 US、加拿大 CA。在所选国家的候选中优先选择标记可用且有较低实测延迟的节点。保存 `fixed_region` 与 `force_countries`；后续恢复可在所选国家之间切换，全部失效时保持断开，不会使用范围外节点。
- **失败处理**：目标不匹配或无候选时不更改路由策略；执行预检且失败时保留旧连接和原策略。预检通过并开始切换后，新策略已保存；若实际出口验证失败，则保持新策略并报告不可用。
- **并发**：多个切换请求互斥；预检/出口验证期间若相关路由策略被修改，旧请求取消，不覆盖后来设置。
- **影响范围**：切换影响所有使用该入口的客户端，已有 TCP 连接可能断开。这里没有实现每个请求独立指定出口、无损迁移或后台任务 ID。

IP 指节点列表中的入口地址；实际出口 IP 由通过代理的 HTTPS 探测获得，二者可能不同。指定 IP 不会把任意服务器地址当成 OpenVPN 节点，也不支持仅凭一个自有服务器 IP 建立代理。

## Web 操作

登录现有管理后台后，在“手动切换出口”区域操作：

1. 输入节点入口 IP，点击“切换并固定此节点”。有多个候选时选择连接方式，再次点击切换。
2. 或勾选一个或多个出口国家，点击“切换并限定所选国家”。
3. 等待结果，并核对活动节点、出口 IP 和代理状态。请求超时不能证明服务端取消，应先查看状态再决定是否重试。

出口国家使用复选框，美国、加拿大始终保留，其他国家来自当前节点列表。后台刷新保留尚未提交的勾选；网络设置弹窗同步支持多选。国家发现筛选与出口国家限制是两个设置。

获取更多节点时，在上方国家发现筛选中清除勾选，选择“所有国家”，再点击“更新节点”。也可以勾选美国、加拿大后更新，只获取对应国家候选。美国、加拿大的发现筛选始终可见，计数为 0 表示当前列表尚无该国家候选。

CSV API 和镜像均不可用时，服务默认回退到官方 HTTPS 网页及配置下载接口，每轮最多导入 100 个配置校验通过的候选，随后仍需连接测试。官方网页仅展示部分节点，刷新结果会变化；支持按国家筛选不保证该国家当时有候选。设置 `VPNGATE_WEB_FALLBACK=0` 可关闭此回退来源。

## 命令行

`proxyctl.py` 读取服务实际生成的 `ui_auth.json`，通过本地 HTTP 登录，完成操作后注销会话。它不导入管理器、不直接改配置文件、不打印登录密码/管理路径；默认忽略客户端进程的 HTTP 代理环境变量，避免把管理请求发给外部代理。

在项目目录中使用：

```bash
python3 proxyctl.py status
python3 proxyctl.py nodes --country JP
python3 proxyctl.py select --country JP
python3 proxyctl.py select --country US --country CA
```

按入口 IP 选择时，将示例保留地址换成节点列表中的真实地址：

```bash
python3 proxyctl.py select --ip 203.0.113.10
```

若返回 409 和多个候选，使用候选的真实 ID：

```bash
python3 proxyctl.py select --ip 203.0.113.10 --node-id 实际候选ID
```

全局参数须放在子命令之前：

```bash
python3 proxyctl.py --auth-file /实际数据目录/ui_auth.json --url http://127.0.0.1:8787 status
```

默认认证文件位于 `VPNGATE_DATA_DIR`，没有该环境变量时使用项目的 `vpngate_data/ui_auth.json`；默认 URL 使用回环地址和认证文件中的 Web 端口。远程 HTTP 会被拒绝，请使用 SSH 隧道或经过验证的 HTTPS 管理入口。CLI 不会自动跟随管理接口重定向来传递凭据。

## API

沿用后台 Cookie 会话，路径为 `/<实际安全路径>/api/select_target`，请求必须是 `application/json`。浏览器跨 Origin 请求被拒绝；没有 Origin 的本机脚本仍需有效会话。

```json
{"mode":"ip","ip":"203.0.113.10"}
```

```json
{"mode":"ip","ip":"203.0.113.10","node_id":"实际候选ID"}
```

```json
{"mode":"country","country":"JP"}
```

多国家选择：

```json
{"mode":"country","countries":["US","CA"]}
```

`countries` 必须为非空国家代码数组；与旧版 `country` 不能同时使用。旧单国家请求与配置仍可用，按 IP 固定会清除国家范围。

仅更新国家策略、保留仍符合范围的现有连接，可向 `POST /api/update_routing` 发送：

```json
{"routing_mode":"fixed_region","force_countries":["US","CA"],"routing_ip_type":"all"}
```

`/api/update_settings` 同样接受 `force_countries`。状态中的 `force_countries` 返回当前国家范围；`force_country` 仅在单选时保留对应代码，多选时为空。

成功返回 `{"ok":true,"message":"...","state":{...}}`。这是同步接口，超时后通过已认证的 `GET /api/nodes` 查询状态，不要推断操作已取消。

| 状态码 | 含义 |
| --- | --- |
| 400 | 字段、IP、国家代码或 JSON 无效；不接受混合选择器和未知字段 |
| 401 | 未登录或会话过期 |
| 403 | 浏览器 Origin 不匹配 |
| 404 | IP / node_id 不在当前节点库中 |
| 409 | IP 有多个候选、另一个任务正在运行，或切换期间配置变化；候选只含公开元数据 |
| 415 | 请求内容类型不是 application/json |
| 502 | 目标预检、OpenVPN、路由或实际代理出口验证失败 |
| 503 | 所选国家范围没有可用或待检测候选；原策略保持不变 |

## 开发部署配置

新增 [`compose.manual.yaml`](../compose.manual.yaml)，用于构建当前源码。它使用容器独立网络空间，只有 `127.0.0.1:8787` 和 `127.0.0.1:7928` 发布到宿主机，不采用 host 网络。容器内监听 `0.0.0.0` 是为了 Docker 端口映射；宿主机发布端口仍仅回环可访问。

它要求显式提供完整代理凭据，使用独立数据卷。原 `compose.yaml` 保留发布镜像和 host 网络结构；要验证当前源码，请使用 `compose.manual.yaml`，避免切换回尚未包含这些功能的旧版镜像。

在具备 Docker、TUN 和相应权限的 Linux 测试主机上执行：

```bash
cd aimili-vpngate
read -r -p '代理用户名: ' LOCAL_PROXY_USER
read -r -s -p '代理密码: ' LOCAL_PROXY_PASS
export LOCAL_PROXY_USER LOCAL_PROXY_PASS
docker compose -f compose.manual.yaml up -d --build
```

管理认证文件保存在独立卷 `/data/ui_auth.json`，使用现有受控方式读取并登录后台；不要将包含密码的文件或输出粘贴到公共日志。也可以直接在容器内使用 CLI：

```bash
docker compose -f compose.manual.yaml exec manual-proxy python3 proxyctl.py nodes --country JP
docker compose -f compose.manual.yaml exec manual-proxy python3 proxyctl.py select --country JP
docker compose -f compose.manual.yaml exec manual-proxy python3 proxyctl.py status
```

远程客户端通过 SSH 转发访问测试主机：

```bash
ssh -N -L 8787:127.0.0.1:8787 -L 7928:127.0.0.1:7928 用户@测试主机
```

客户端配置 HTTP 代理 `http://127.0.0.1:7928` 或 SOCKS5h `127.0.0.1:7928`，并填写显式设置的代理用户名密码。代理认证不等于传输加密；远程接入保留 SSH 隧道。

## 兼容性与安全边界

- 新建配置的 Web 默认仅监听 `127.0.0.1`，管理路径随机生成。已有配置中的监听地址和路径保持原值；升级后请核对实际配置。安装器可以写入自己的监听配置，不应仅凭源码默认值判断实际监听地址。
- 原 `compose.yaml` 使用 host 网络，Web 默认也改为回环监听。远程访问请使用 SSH 隧道，或显式配置可信 HTTPS 反向代理。`compose.manual.yaml` 中容器内监听 `0.0.0.0`，宿主机映射仍仅回环可访问。
- HTTP 节点源默认禁用；确有兼容需求时可显式设置 `ALLOW_INSECURE_NODE_SOURCES=1`。HTTPS 拉取拒绝降级重定向。`VPNGATE_WEB_FALLBACK=0` 可关闭官方网页回退。
- 隧道 DNS 失败时拒绝回退到系统解析；连接数值地址时使用 `AI_NUMERICHOST`。出口健康检查使用验证证书的 HTTPS，并严格解析返回的 IP 地址。
- 代理用户名和密码必须同时设置且非空；两者均未设置时仍保留原有的无认证行为。开发 Compose 强制提供完整凭据；远程客户端仍需通过 SSH 等加密链路接入。
- 独立容器网络不等于控制面与 VPN worker 已分离。管理器仍需 VPN 和网络操作权限；不要让多个实例共用数据目录或同一网络空间。
- IP 类型查询、登录限速、密码存储及缓存有效期等其他边界尚未在这项改动中全面改造。VPNGate 志愿者节点没有稳定 IP、匿名性或持续可用性承诺。

## 验证

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile vpngate_manager.py vpn_utils.py proxy_server.py snapshot_utils.py manual_target.py proxyctl.py official_web.py
bash -n install.sh
python3 scripts/build_release_archives.py --output-dir dist
```

回归覆盖目标解析、同 IP 多端口消歧、多国家候选选择和范围内恢复、拒绝范围外连接、旧配置兼容、并发策略变化、HTTP 认证与错误响应、CLI、表单状态、DNS 和 HTTPS 安全边界、官方网页解析及配置校验。

测试使用临时数据、模拟 OpenVPN/路由及回环 HTTP 服务器，不会启动真实 VPN。表单测试需要 Node.js；未安装时对应测试跳过。Docker Compose 提供开发部署配置，但本地尚未完成 Docker 镜像构建验收；真实节点、IPv6、断线行为和容器网络仍需在具备 TUN 的测试环境验证。CI 对 Python 3.9、3.11 和 3.13 运行测试与构建检查。
