<div align="center">

# AimiliVPN

**Linux VPS용 VPNGate 노드 관리 및 HTTP / HTTPS / SOCKS5 프록시 게이트웨이**

[![Release](https://img.shields.io/github/v/release/baoweise-bot/aimili-vpngate?style=flat-square&label=stable&color=16a34a)](https://github.com/baoweise-bot/aimili-vpngate/releases/latest)
[![Docker](https://img.shields.io/badge/Docker-amd64%20%7C%20386%20%7C%20arm64%20%7C%20armv7-0ea5e9?style=flat-square&logo=docker&logoColor=white)](https://github.com/baoweise-bot/aimili-vpngate/pkgs/container/aimili-vpngate)
[![License](https://img.shields.io/badge/License-GPL--3.0-334155?style=flat-square)](../LICENSE)

[简体中文](../README.md) · [English](README.en.md) · [日本語](README.ja.md) · **한국어**

[빠른 설치](#quick-install) · [설치](#installation) · [연결](#connection) · [추천 서비스](#vps) · [커뮤니티](#community) · [법적 고지](#legal)

[![Website](https://img.shields.io/badge/Website-339936.xyz-f97316?style=for-the-badge)](https://339936.xyz)
[![Telegram](https://img.shields.io/badge/Telegram-Community-229ED9?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/arestemple)
[![YouTube](https://img.shields.io/badge/YouTube-Tutorial-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](https://www.youtube.com/watch?v=s-ATfXR8BpI)

</div>

AimiliVPN은 Python 표준 라이브러리로 VPNGate 노드를 관리하며 노드 검색과 테스트, 연결 전환, Web 관리 화면, HTTP / HTTPS 웹사이트 프록시 및 SOCKS5 접속을 제공합니다.

| 항목 | 기본값 또는 지원 범위 |
| --- | --- |
| Web 관리 화면 | TCP `8787`, 전용 경로, 사용자 이름, 비밀번호 |
| 로컬 프록시 | `127.0.0.1:7928`, HTTP, HTTPS `CONNECT`, SOCKS5 |
| 소스 배포 | x64, x86, ARM64, ARM32 Linux |
| Docker | `linux/amd64`, `linux/386`, `linux/arm64`, `linux/arm/v7` |

> [!IMPORTANT]
> **네트워크 가용성:** 일부 지역, 데이터 센터 및 네트워크 제공업체는 DNS, VPNGate API, GitHub 미러 또는 VPN 프로토콜을 제한할 수 있습니다. 미러와 로컬 스냅샷은 노드 목록 가용성을 높이지만 모든 환경의 연결 성공을 보장하지 않습니다. 배포 전에 현지 법률과 VPS 제공업체가 VPN/TUN을 허용하는지 확인하십시오.

<a id="quick-install"></a>
## 빠른 설치

지원되는 Linux VPS에서 `root`로 실행합니다.

```bash
bash <(curl -Ls https://raw.githubusercontent.com/baoweise-bot/aimili-vpngate/main/install.sh)
```

설치 후 Web 관리 화면의 전체 URL, 전용 경로, 사용자 이름과 비밀번호가 표시됩니다. `ml` 명령으로 관리 메뉴를 열 수 있습니다.

> [!TIP]
> VPS 제어판에서 TUN/TAP을 활성화하고 `/dev/net/tun`이 존재하는지 확인하십시오. Web 기본 포트는 TCP `8787`이며 가능하면 자신의 IP만 허용하십시오.

<a id="vps"></a>
## 추천 서비스

| 서비스 | 유형 | 추천 이유 | 링크 |
| --- | --- | --- | --- |
| **BandwagonHost** | VPS | China Telecom CN2 GIA, China Unicom 9929, China Mobile CMIN2 최적화 회선. 지연 시간이 짧고 안정적이며 TikTok 라이브, 해외 전자상거래 및 장기 글로벌 서비스에 적합합니다. | [자세히 보기](https://bandwagonhost.com/aff.php?aff=81790) |
| **RackNerd** | VPS | 월 4000GB의 넉넉한 트래픽과 뛰어난 비용 효율. 장기 실행 서비스의 배포 비용을 낮추기 좋습니다. | [자세히 보기](https://my.racknerd.com/aff.php?aff=18708) |
| **OpenMili** | AI 중계 | GPT 모델을 바꾸지 않고 제공하는 AI 중계 서비스. 저렴한 1:2 요율과 이미지 생성 기능을 지원합니다. | [OpenMili 방문](https://openmili.com/) |

일부 링크는 제휴 링크이며, 이를 통해 구매해도 가격은 올라가지 않습니다.

구매 전에 선택한 요금제가 TUN/TAP, OpenVPN 및 필요한 네트워크 프로토콜을 허용하는지 확인하십시오.

<a id="installation"></a>
## 설치

### 요구 사항

- Ubuntu, Debian, Alpine, CentOS, RHEL, Rocky Linux, AlmaLinux, Fedora, Oracle Linux 또는 Amazon Linux.
- `root`, OpenVPN, iptables, 정책 라우팅 및 TUN/TAP.
- Windows와 macOS는 프록시 클라이언트로 사용할 수 있지만 전체 게이트웨이를 실행할 수 없습니다.

### 방법 1: 소스 설치 프로그램

```bash
bash <(curl -Ls https://raw.githubusercontent.com/baoweise-bot/aimili-vpngate/main/install.sh)
```

`/opt/aimilivpn`에 배포하고 시스템 서비스를 등록합니다.

```bash
ml                 # 관리 메뉴
ml status          # 상태, Web URL, 사용자 이름
ml logs            # 로그 보기
ml restart         # 서비스 재시작
ml password        # Web 인증 정보 재설정
ml update          # main 안정 브랜치에서 업데이트
ml uninstall       # 제거
```

먼저 설치 프로그램을 검토하려면:

```bash
git clone --branch main --single-branch https://github.com/baoweise-bot/aimili-vpngate.git
cd aimili-vpngate
sudo bash install.sh
```

공통 Linux 소스 아카이브와 SHA-256 체크섬은 [GitHub Releases](https://github.com/baoweise-bot/aimili-vpngate/releases/latest)에서 받을 수 있습니다. 변경 사항은 Release Notes에 기록됩니다.

### 방법 2: Docker Compose

Docker 호스트는 `/dev/net/tun`, host 네트워크, `NET_ADMIN`, `NET_RAW`를 제공해야 합니다.

```bash
git clone --branch main --single-branch https://github.com/baoweise-bot/aimili-vpngate.git
cd aimili-vpngate
docker compose pull
docker compose up -d
docker logs -f aimilivpn
```

이미지: `ghcr.io/baoweise-bot/aimili-vpngate:2.1`

업데이트:

```bash
docker compose pull
docker compose up -d
```

<details>
<summary><strong>docker run 명령 보기</strong></summary>

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
<summary><strong>GHCR을 사용할 수 없을 때 로컬 빌드</strong></summary>

```bash
git clone --branch main --single-branch https://github.com/baoweise-bot/aimili-vpngate.git
cd aimili-vpngate
docker compose build
docker compose up -d
```

</details>

<a id="connection"></a>
## 연결 및 사용

### 1. Web 관리 화면 로그인

소스 설치에서는 설치 프로그램이 출력한 URL을 엽니다.

```text
http://VPS_IP:8787/private_path/
```

URL은 `ml status`, 인증 정보 재설정은 `ml password`를 사용합니다. Docker 사용자는 다음 명령으로 초기 설정을 확인할 수 있습니다.

```bash
docker exec aimilivpn cat /data/ui_auth.json
```

`secret_path`, `username`, `password`로 로그인하고 첫 로그인 후 변경하십시오.

### 2. 노드 가져오기 및 연결

1. 로그인 후 첫 노드 목록을 기다리거나 “노드 업데이트”를 실행합니다.
2. 국가별로 필터링하고 “테스트”로 VPS에서의 연결 가능 여부와 지연 시간을 확인합니다.
3. 대상 노드의 “전환”을 선택합니다. 사전 확인에 실패하면 가능한 경우 현재 연결을 유지합니다.
4. 스마트 자동, 국가 고정 또는 IP 고정 라우팅을 선택합니다.
5. 상태 영역에서 VPN 연결과 출구 IP를 확인합니다.

> [!NOTE]
> **러시아 노드 자동 필터링:** 탐지에 성공하면 IP 정보를 통해 노드의 물리적 위치를 확인하며, 러시아로 판정되면 자동으로 사용 불가로 표시되어 스마트 자동, 빠른 연결, 주기적 검사 대상에서 제외됩니다. 투명성을 위해 위치 정보는 노드 목록에 계속 표시됩니다.

### 3. VPS에서 프록시 사용

HTTP, HTTPS 웹사이트 프록시와 SOCKS5는 `127.0.0.1:7928`을 공유합니다.

```bash
# HTTP / HTTPS
curl -x http://127.0.0.1:7928 https://api.ipify.org

# SOCKS5 및 원격 DNS
curl --proxy socks5h://127.0.0.1:7928 https://api.ipify.org
```

### 4. 다른 컴퓨터에서 연결

프록시를 공개하지 말고 SSH 터널을 사용하십시오.

```bash
ssh -N \
  -L 8787:127.0.0.1:8787 \
  -L 7928:127.0.0.1:7928 \
  root@VPS_IP
```

- Web: `http://127.0.0.1:8787/private_path/`
- HTTP / HTTPS: `127.0.0.1:7928`
- SOCKS5: `127.0.0.1:7928`, 가능하면 원격 DNS 또는 `socks5h` 사용

> [!WARNING]
> `7928`은 기본적으로 공개 사용자 인증을 제공하지 않습니다. 방화벽, 접속 원본 IP 제한 또는 기타 신뢰할 수 있는 접근 제어 없이 공개하지 마십시오.

<a id="community"></a>
## 웹사이트, 커뮤니티 및 동영상

| 대상 | 용도 | 링크 |
| --- | --- | --- |
| 웹사이트 / 포럼 | 공지와 토론 | [339936.xyz](https://339936.xyz) |
| Telegram 그룹 | 실시간 커뮤니티 | [t.me/arestemple](https://t.me/arestemple) |
| YouTube 튜토리얼 | 설치 및 사용 동영상 | [보기](https://www.youtube.com/watch?v=s-ATfXR8BpI) |
| GitHub Issues | 재현 가능한 버그와 기능 요청 | [Issue 만들기](https://github.com/baoweise-bot/aimili-vpngate/issues) |
| 이메일 | 버그 신고 및 연락 | [yaohunse7@gmail.com](mailto:yaohunse7@gmail.com) |

<a id="legal"></a>
## 사용 범위 및 법적 고지

> [!CAUTION]
> 이 프로젝트를 다운로드, 배포 또는 사용하기 전에 사용 지역과 VPS 소재지의 법률, 제공업체 약관 및 VPNGate 규칙을 준수하는지 직접 확인해야 합니다. 이 내용은 프로젝트의 사용 범위를 설명할 뿐 법률 자문이 아니며 법적 책임의 면제를 보장하지 않습니다.

1. **허용 목적:** 합법적인 네트워크 연구, 교육, 개발 테스트, 개인정보 보호 및 승인된 접속에만 사용하십시오. 법에 따라 시행되는 통제 회피, 무단 접속, 공격, 스캔, 스팸, 사기, 권리 침해 또는 기타 불법 활동에 사용해서는 안 됩니다.
2. **네트워크 및 지역 제한:** 일부 지역과 데이터 센터는 VPNGate, GitHub 미러 또는 원격 VPN 노드를 제한할 수 있습니다. 이 프로젝트는 어떤 지역이나 호스트에서도 지속적인 가용성을 보장하지 않습니다. 현지 법률과 제공업체 약관이 허용하는 환경에서만 사용하십시오.
3. **제3자 노드:** VPNGate 노드는 제3자 자원봉사자가 운영합니다. 이 프로젝트는 해당 노드를 소유, 통제 또는 감사하지 않으며 가용성, 속도, 보안, 개인정보 처리 또는 로그 기록을 보장하지 않습니다. 신뢰할 수 없는 노드로 민감한 정보를 전송하지 마십시오.
4. **사용자 책임:** 노드 선택, 트래픽, 배포 위치, 공개 포트 및 계정 보안은 사용자의 책임입니다. 불법 사용, 잘못된 설정, 제3자 노드, 서비스 중단, 데이터 유출 또는 계정 남용에 대한 법적 책임은 사용자에게 있습니다.
5. **무보증:** 소프트웨어는 “있는 그대로” 제공됩니다. 적용 법률이 허용하는 최대 범위에서 유지관리자는 가용성, 상품성, 특정 목적 적합성 또는 간접 손해를 보증하지 않습니다. 법적으로 제외할 수 없는 책임에는 영향을 주지 않습니다.
6. **불확실한 경우 중단:** 현지 법률이나 제공업체 정책이 이를 허용하는지 확인할 수 없다면 배포 및 사용을 중단하고 해당 관할권의 자격 있는 법률 전문가와 상담하십시오.

<div align="center">

[Stable Release](https://github.com/baoweise-bot/aimili-vpngate/releases/latest) · [Issues](https://github.com/baoweise-bot/aimili-vpngate/issues) · [GPL-3.0 License](../LICENSE)

</div>
