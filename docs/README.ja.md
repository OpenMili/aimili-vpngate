<div align="center">

# AimiliVPN

**Linux VPS 向け VPNGate ノード管理・HTTP / HTTPS / SOCKS5 プロキシゲートウェイ**

[![Release](https://img.shields.io/github/v/release/baoweise-bot/aimili-vpngate?style=flat-square&label=stable&color=16a34a)](https://github.com/baoweise-bot/aimili-vpngate/releases/latest)
[![Docker](https://img.shields.io/badge/Docker-amd64%20%7C%20386%20%7C%20arm64%20%7C%20armv7-0ea5e9?style=flat-square&logo=docker&logoColor=white)](https://github.com/baoweise-bot/aimili-vpngate/pkgs/container/aimili-vpngate)
[![License](https://img.shields.io/badge/License-GPL--3.0-334155?style=flat-square)](../LICENSE)

[简体中文](../README.md) · [English](README.en.md) · **日本語** · [한국어](README.ko.md)

[クイックインストール](#quick-install) · [インストール](#installation) · [接続方法](#connection) · [おすすめサービス](#vps) · [コミュニティ](#community) · [法的通知](#legal)

[![Website](https://img.shields.io/badge/Website-339936.xyz-f97316?style=for-the-badge)](https://339936.xyz)
[![Telegram](https://img.shields.io/badge/Telegram-Community-229ED9?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/arestemple)
[![YouTube](https://img.shields.io/badge/YouTube-Tutorial-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](https://www.youtube.com/watch?v=s-ATfXR8BpI)

</div>

AimiliVPN は Python 標準ライブラリで VPNGate ノードを管理し、ノード取得・テスト、接続切り替え、Web 管理画面、HTTP / HTTPS サイト用プロキシと SOCKS5 を提供します。

| 項目 | デフォルトまたは対応範囲 |
| --- | --- |
| Web 管理画面 | TCP `8787`、専用パス、ユーザー名、パスワード |
| ローカルプロキシ | `127.0.0.1:7928`、HTTP、HTTPS `CONNECT`、SOCKS5 |
| ソース版 | x64、x86、ARM64、ARM32 Linux |
| Docker | `linux/amd64`、`linux/386`、`linux/arm64`、`linux/arm/v7` |

> [!IMPORTANT]
> **ネットワーク可用性：** 地域、データセンター、ネットワーク事業者によっては、DNS、VPNGate API、GitHub ミラー、VPN プロトコルが制限される場合があります。ミラーとローカルスナップショットはノード一覧の可用性を高めますが、すべての環境で接続を保証するものではありません。展開前に、現地法と VPS 事業者が VPN/TUN を許可していることを確認してください。

<a id="quick-install"></a>
## クイックインストール

対応する Linux VPS で `root` として実行します。

```bash
bash <(curl -Ls https://raw.githubusercontent.com/baoweise-bot/aimili-vpngate/main/install.sh)
```

完了後、Web 管理画面の URL、専用パス、ユーザー名、パスワードが表示されます。`ml` で管理メニューを開けます。

> [!TIP]
> VPS の管理画面で TUN/TAP を有効にし、`/dev/net/tun` が存在することを確認してください。Web のデフォルトポートは TCP `8787` です。可能な限り自分の IP だけを許可してください。

<a id="vps"></a>
## おすすめサービス

| サービス | 種類 | おすすめポイント | リンク |
| --- | --- | --- | --- |
| **BandwagonHost** | VPS | China Telecom CN2 GIA、China Unicom 9929、China Mobile CMIN2 の最適化回線。低遅延で安定しており、TikTok ライブ、越境 EC、長期的な海外向けサービスに適しています。 | [詳細を見る](https://bandwagonhost.com/aff.php?aff=81790) |
| **RackNerd** | VPS | 月間 4000GB の大容量トラフィックと高いコストパフォーマンス。継続稼働するサービスの導入コストを抑えられます。 | [詳細を見る](https://my.racknerd.com/aff.php?aff=18708) |
| **OpenMili** | AI 中継 | GPT モデルを差し替えずに提供する AI 中継サービス。低価格な 1:2 レートで、画像生成にも対応しています。 | [OpenMili を見る](https://openmili.com/) |

一部のリンクはアフィリエイトリンクです。リンク経由でも購入価格は上がりません。

購入前に、対象プランが TUN/TAP、OpenVPN、必要なプロトコルを許可していることを確認してください。

<a id="installation"></a>
## インストール

### 動作要件

- Ubuntu、Debian、Alpine、CentOS、RHEL、Rocky Linux、AlmaLinux、Fedora、Oracle Linux、Amazon Linux。
- `root`、OpenVPN、iptables、ポリシールーティング、TUN/TAP。
- Windows と macOS はプロキシクライアントとして利用できますが、ゲートウェイ本体は実行できません。

### 方法 1：ソースインストーラー

```bash
bash <(curl -Ls https://raw.githubusercontent.com/baoweise-bot/aimili-vpngate/main/install.sh)
```

`/opt/aimilivpn` に配置し、システムサービスを登録します。

```bash
ml                 # 管理メニュー
ml status          # 状態、Web URL、ユーザー名
ml logs            # ログ
ml restart         # 再起動
ml password        # Web 認証情報を再設定
ml update          # main 安定版から更新
ml uninstall       # アンインストール
```

事前にスクリプトを確認する場合：

```bash
git clone --branch main --single-branch https://github.com/baoweise-bot/aimili-vpngate.git
cd aimili-vpngate
sudo bash install.sh
```

Linux 共通ソースアーカイブと SHA-256 は [GitHub Releases](https://github.com/baoweise-bot/aimili-vpngate/releases/latest) から取得できます。変更内容は Release Notes に掲載されます。

### 方法 2：Docker Compose

Docker ホストには `/dev/net/tun`、host ネットワーク、`NET_ADMIN`、`NET_RAW` が必要です。

```bash
git clone --branch main --single-branch https://github.com/baoweise-bot/aimili-vpngate.git
cd aimili-vpngate
docker compose pull
docker compose up -d
docker logs -f aimilivpn
```

イメージ：`ghcr.io/baoweise-bot/aimili-vpngate:2.1`

更新：

```bash
docker compose pull
docker compose up -d
```

<details>
<summary><strong>docker run コマンドを表示</strong></summary>

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
<summary><strong>GHCR を利用できない場合のローカルビルド</strong></summary>

```bash
git clone --branch main --single-branch https://github.com/baoweise-bot/aimili-vpngate.git
cd aimili-vpngate
docker compose build
docker compose up -d
```

</details>

<a id="connection"></a>
## 接続と利用方法

### 1. Web 管理画面へログイン

ソース版では、インストーラーが表示した URL を開きます。

```text
http://VPS_IP:8787/private_path/
```

URL は `ml status`、認証情報の再設定は `ml password` を使用します。Docker では次のコマンドで初期設定を確認できます。

```bash
docker exec aimilivpn cat /data/ui_auth.json
```

`secret_path`、`username`、`password` を使用し、初回ログイン後に変更してください。

### 2. ノードを取得して接続

1. ログイン後、最初の一覧を待つか「ノード更新」を実行します。
2. 国で絞り込み、「テスト」で VPS からの到達性と遅延を確認します。
3. 対象ノードの「切り替え」を選択します。事前確認に失敗した場合、可能な限り現在の接続を維持します。
4. スマート自動、国固定、IP 固定からルーティングモードを選びます。
5. 接続状態と出口 IP を確認します。

> [!NOTE]
> **ロシアのノードを自動フィルタリング：** 探測に成功すると IP 情報からノードの物理的な位置を判定し、ロシアと判定された場合は自動的に利用不可としてマークされ、スマート自動、クイック接続、定期チェックの対象から除外されます。透明性のため、位置情報はノード一覧に引き続き表示されます。

### 3. VPS 上でプロキシを使用

HTTP、HTTPS サイト用プロキシ、SOCKS5 は `127.0.0.1:7928` を共有します。

```bash
# HTTP / HTTPS
curl -x http://127.0.0.1:7928 https://api.ipify.org

# SOCKS5、DNS もプロキシ経由
curl --proxy socks5h://127.0.0.1:7928 https://api.ipify.org
```

### 4. 別の端末から接続

プロキシを公開せず、SSH トンネルを利用してください。

```bash
ssh -N \
  -L 8787:127.0.0.1:8787 \
  -L 7928:127.0.0.1:7928 \
  root@VPS_IP
```

- Web：`http://127.0.0.1:8787/private_path/`
- HTTP / HTTPS：`127.0.0.1:7928`
- SOCKS5：`127.0.0.1:7928`。可能な場合はリモート DNS または `socks5h` を使用

> [!WARNING]
> `7928` には、デフォルトで公開用のユーザー認証がありません。ファイアウォール、接続元 IP 制限などの確実なアクセス制御なしで公開しないでください。

<a id="community"></a>
## Web サイト・コミュニティ・動画

| 入口 | 用途 | リンク |
| --- | --- | --- |
| Web サイト / フォーラム | お知らせと交流 | [339936.xyz](https://339936.xyz) |
| Telegram | リアルタイム交流 | [t.me/arestemple](https://t.me/arestemple) |
| YouTube | インストール・利用方法 | [動画を見る](https://www.youtube.com/watch?v=s-ATfXR8BpI) |
| GitHub Issues | 再現可能な不具合と機能要望 | [Issue を作成](https://github.com/baoweise-bot/aimili-vpngate/issues) |
| メール | 不具合報告と連絡 | [yaohunse7@gmail.com](mailto:yaohunse7@gmail.com) |

<a id="legal"></a>
## 利用範囲と法的通知

> [!CAUTION]
> 本プロジェクトをダウンロード、展開、使用する前に、利用地と VPS 所在地の法律、事業者の規約、VPNGate の規則への適合を利用者自身で確認してください。本節は利用範囲を示すもので、法律上の助言ではなく、法的責任の免除を保証するものではありません。

1. **許可される用途：** 合法なネットワーク研究、教育、開発テスト、プライバシー保護、許可されたアクセスに限ります。法的な規制の回避、不正アクセス、攻撃、スキャン、スパム、詐欺、権利侵害、その他の違法行為に使用してはいけません。
2. **ネットワークと地域の制限：** 地域やデータセンターによっては VPNGate、GitHub ミラー、VPN ノードが制限される場合があります。本プロジェクトは、いかなる地域・環境でも継続的な可用性を保証しません。現地法と事業者規約が許可する場合に限り使用してください。
3. **第三者ノード：** VPNGate ノードは第三者のボランティアが運営しています。本プロジェクトはノードを所有・管理・監査せず、可用性、速度、安全性、プライバシー方針、ログ動作を保証しません。機密情報を信頼できないノードで送信しないでください。
4. **利用者の責任：** ノード選択、通信内容、設置場所、公開ポート、アカウント管理は利用者の責任です。違法利用、設定不備、第三者ノード、停止、情報漏えい、不正利用に伴う責任は利用者が負います。
5. **無保証：** 本ソフトウェアは「現状有姿」で提供されます。適用法で認められる最大限の範囲で、保守者は可用性、商品性、特定目的適合性、間接損害を保証しません。法律上排除できない責任には影響しません。
6. **不明な場合：** 現地法や事業者規約で許可されているか確認できない場合は使用を中止し、該当法域の有資格法律専門家に相談してください。

<div align="center">

[Stable Release](https://github.com/baoweise-bot/aimili-vpngate/releases/latest) · [Issues](https://github.com/baoweise-bot/aimili-vpngate/issues) · [GPL-3.0 License](../LICENSE)

</div>
