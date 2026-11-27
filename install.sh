#!/usr/bin/env bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;36m'
PLAIN='\033[0m'

# 1. Check root permissions
if [ "$(id -u)" != "0" ]; then
    echo -e "${RED}错误: 必须以 root 权限运行此脚本。请使用: sudo bash $0${PLAIN}"
    exit 1
fi

INSTALL_DIR="/opt/aimilivpn"
local_dev=0
case "${1:-}" in
    --local-dev) local_dev=1 ;;
    '') ;;
    *) echo "用法: bash install.sh [--local-dev]" >&2; exit 1 ;;
esac
if [ "$#" -gt 1 ]; then
    echo "用法: bash install.sh [--local-dev]" >&2
    exit 1
fi
# Running this file from a pipe or as a standalone download installs a verified Release.
# The packager pins this value in the downloadable install-source.sh asset.
bootstrap_release=latest
script_path=${BASH_SOURCE[0]:-}
SOURCE_DIR=''
if [[ -n $script_path && -f $script_path ]]; then
    SOURCE_DIR=$(cd -- "$(dirname -- "$script_path")" && pwd -P)
fi
standalone=0
if [[ -z $SOURCE_DIR || ( ! -e $SOURCE_DIR/vpngate_manager.py && ! -e $SOURCE_DIR/release_utils.py ) ]]; then
    standalone=1
fi
if [[ $standalone == 1 || $bootstrap_release != latest ]]; then
    if [[ $local_dev == 1 ]]; then
        echo '--local-dev 需要完整的本地源码目录。' >&2
        exit 1
    fi
    set -euo pipefail
    for tool in curl sha256sum tar mktemp; do
        command -v "$tool" >/dev/null || { echo "缺少命令 $tool，请先安装。" >&2; exit 1; }
    done
    release_url=https://github.com/OpenMili/aimili-vpngate/releases
    channel=latest/download
    if [[ $bootstrap_release != latest ]]; then
        channel="download/$bootstrap_release"
    fi
    work_dir=$(mktemp -d)
    trap 'rm -rf -- "$work_dir"' EXIT
    cd -- "$work_dir"

    download() {
        curl -q --proto '=https' --proto-redir '=https' --fail --silent --show-error --location \
            --retry 2 --connect-timeout 15 --max-time 120 --max-filesize "$3" --output "$2" "$1"
    }
    if [[ $bootstrap_release == latest && ${AIMILIVPN_NONINTERACTIVE:-0} != 1 ]]; then
        download "$release_url/latest/download/install.sh" menu.sh 262144
        if [[ -t 0 ]]; then bash menu.sh; else bash menu.sh </dev/tty; fi
        exit 0
    fi
    download "$release_url/$channel/sha256sums.txt" sha256sums.txt 4096
    manifest=$(<sha256sums.txt)
    pattern='^([0-9a-fA-F]{64})[[:blank:]]+\*?aimilivpn-(v[0-9]{1,9}\.[0-9]{1,9}\.[0-9]{1,9})-linux-source\.tar\.gz$'
    if [[ ! $manifest =~ $pattern ]]; then
        echo '发行版校验清单格式错误。' >&2; exit 1
    fi
    checksum=${BASH_REMATCH[1]}
    release_tag=${BASH_REMATCH[2]}
    if [[ $bootstrap_release != latest && $bootstrap_release != "$release_tag" ]]; then
        echo '校验清单与请求的发行版不一致。' >&2; exit 1
    fi
    folder="aimilivpn-$release_tag-linux-source"
    printf '正在下载并校验 AimiliVPN %s 源码发行包。\n' "$release_tag"
    download "$release_url/download/$release_tag/$folder.tar.gz" release.tar.gz 16777216
    printf '%s  release.tar.gz\n' "$checksum" | sha256sum -c -

    # Accept only regular files and directories under the expected package root.
    LC_ALL=C tar -tvzf release.tar.gz > types
    if grep -qv '^[-d]' types; then
        echo '发行包包含不支持的文件类型。' >&2; exit 1
    fi
    tar -tzf release.tar.gz > members
    while IFS= read -r member; do
        if [[ ( $member != "$folder" && $member != "$folder/"* ) || /$member/ == */../* || $member == *\\* ]]; then
            echo '发行包包含无效路径。' >&2; exit 1
        fi
    done < members
    tar -xzf release.tar.gz
    cd -- "$folder"
    if [[ $(< VERSION) != "${release_tag#v}" || ! -f install.sh || ! -f vpngate_manager.py ]]; then
        echo '发行包内容与版本不符。' >&2; exit 1
    fi
    bash ./install.sh
    exit 0
fi

if command -v flock >/dev/null; then
    exec 8>>/run/aimilivpn-installer.lock
    flock -n 8 || { echo '另一个 AimiliVPN 安装或卸载正在运行。' >&2; exit 1; }
fi
# Both deployment modes share host tunnel and policy-routing resources.
if command -v docker >/dev/null && docker container inspect aimilivpn >/dev/null 2>&1; then
    docker_image=$(docker inspect --format '{{.Config.Image}}' aimilivpn)
    if [[ $docker_image == *aimili-vpngate* ]]; then
        echo '已安装 AimiliVPN Docker 版。请先卸载原实例，再选择系统版。' >&2
        exit 1
    fi
fi

# 2. Check OS distribution and set package manager
OS_TYPE=""
PKG_MGR=""
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_TYPE=$ID
fi

case "$OS_TYPE" in
    ubuntu|debian)
        export NEEDRESTART_MODE=l
        PKG_MGR="apt-get"
        export DEBIAN_FRONTEND=noninteractive
        ;;
    alpine)
        PKG_MGR="apk"
        ;;
    centos|rhel|rocky|almalinux|fedora|ol|amzn)
        if command -v dnf >/dev/null 2>&1; then
            PKG_MGR="dnf"
        else
            PKG_MGR="yum"
        fi
        ;;
    *)
        echo -e "${RED}错误: 不支持的操作系统 ($OS_TYPE)！目前仅支持 Ubuntu/Debian/Alpine/CentOS/RHEL/Rocky/AlmaLinux/Fedora/OracleLinux/AmazonLinux。${PLAIN}"
        exit 1
        ;;
esac

echo -e "${BLUE}==========================================================${PLAIN}"
echo -e "${BLUE}        欢迎使用 AimiliVPN 一键源码部署与管理脚本${PLAIN}"
echo -e "${BLUE}==========================================================${PLAIN}"

if [ -f "${INSTALL_DIR}/.local_dev" ]; then
    if [ "$SOURCE_DIR" != "$INSTALL_DIR" ] && [ "$local_dev" = 0 ]; then
        echo "已启用本地开发模式。请保留本地源码，或先备份后移除 ${INSTALL_DIR}/.local_dev。" >&2
        exit 1
    fi
    local_dev=1
fi
app_files=(VERSION README.md LICENSE install.sh vpngate_manager.py vpn_utils.py proxy_server.py snapshot_utils.py auth_store.py release_utils.py panel_access.py)
for file in "${app_files[@]}" mirror/vpngate.csv mirror/vpngate.meta.json; do
    if [ ! -f "$SOURCE_DIR/$file" ]; then
        echo "缺少 $file。请从同一份发行包中校验并解压后运行安装脚本。" >&2
        exit 1
    fi
done

echo -e "\n${YELLOW}[1/4] 正在安装系统基础依赖...${PLAIN}"
if [ "$PKG_MGR" = "apt-get" ]; then
    echo -e "  -> 正在运行 apt-get update 更新软件源清单..."
    apt-get update -q || true
    echo -e "  -> 正在运行 apt-get install 安装基础依赖包..."
    apt-get install -y openvpn curl ca-certificates iptables iproute2 iputils-ping psmisc python3
elif [ "$PKG_MGR" = "apk" ]; then
    echo -e "  -> 正在运行 apk update 更新软件源清单..."
    apk update || true
    echo -e "  -> 正在运行 apk add 安装基础依赖包..."
    # bash is required for this script itself and some internal logic
    apk add openvpn curl ca-certificates iptables iproute2 iputils psmisc python3 bash
elif [ "$PKG_MGR" = "dnf" ] || [ "$PKG_MGR" = "yum" ]; then
    echo -e "  -> 正在运行 $PKG_MGR 安装基础依赖包..."
    if [ "$OS_TYPE" != "fedora" ] && [ "$OS_TYPE" != "amzn" ]; then
        echo -e "     -> 正在安装 EPEL 软件源 (以支持 openvpn)..."
        $PKG_MGR install -y epel-release || true
    fi
    # Try installing packages. Note: iproute or iproute2
    $PKG_MGR install -y openvpn curl ca-certificates iptables iproute iputils psmisc python3 || \
    $PKG_MGR install -y openvpn curl ca-certificates iptables iproute2 iputils psmisc python3
fi

# Compile and stop the old service before replacing its source files.
python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' || {
    echo "需要 Python 3.9 或更高版本。" >&2
    exit 1
}
python3 -m py_compile "$SOURCE_DIR/"*.py

echo -e "\n${YELLOW}[2/4] 正在部署本地发行包到 ${INSTALL_DIR}...${PLAIN}"
if ! command -v systemctl >/dev/null 2>&1 && ! command -v rc-service >/dev/null 2>&1; then
    echo "需要可用的 systemd 或 OpenRC。" >&2
    exit 1
fi
if [ "$SOURCE_DIR" != "$INSTALL_DIR" ]; then
    if command -v systemctl >/dev/null 2>&1; then
        if systemctl is-active --quiet aimilivpn.service; then
            systemctl stop aimilivpn.service
        fi
    elif rc-service aimilivpn status >/dev/null 2>&1; then
        rc-service aimilivpn stop
    fi
    install -d -m 755 "$INSTALL_DIR" "$INSTALL_DIR/mirror"
    for file in "${app_files[@]}"; do
        install -m 644 "$SOURCE_DIR/$file" "$INSTALL_DIR/$file"
    done
    install -m 644 "$SOURCE_DIR/mirror/vpngate.csv" "$SOURCE_DIR/mirror/vpngate.meta.json" "$INSTALL_DIR/mirror/"
fi
if [ "$local_dev" = 1 ]; then
    touch "$INSTALL_DIR/.local_dev"
fi
cd "$INSTALL_DIR"

# 5. Configure Service
echo -e "\n${YELLOW}[3/4] 正在配置系统服务...${PLAIN}"
if command -v systemctl >/dev/null 2>&1; then
    echo -e "  -> 检测到 systemd，正在创建服务配置 /lib/systemd/system/aimilivpn.service ..."
    cat > /lib/systemd/system/aimilivpn.service <<EOF
[Unit]
Description=AimiliVPN OpenVPN Manager with HTTP/SOCKS5 Proxy
After=network.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
ExecStart=/usr/bin/python3 vpngate_manager.py
Restart=always
RestartSec=5
Environment=DEPLOYMENT_MODE=source
Environment=PYTHONDONTWRITEBYTECODE=1
EnvironmentFile=-/etc/default/aimilivpn

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable aimilivpn.service
elif command -v rc-service >/dev/null 2>&1; then
    echo -e "  -> 检测到 OpenRC，正在创建服务配置 /etc/init.d/aimilivpn ..."
    cat > /etc/init.d/aimilivpn <<EOF
#!/sbin/openrc-run

description="AimiliVPN OpenVPN Manager with HTTP/SOCKS5 Proxy"
command="/usr/bin/python3"
command_args="${INSTALL_DIR}/vpngate_manager.py"
supervisor="supervise-daemon"
respawn_delay=3
respawn_max=0
directory="${INSTALL_DIR}"
pidfile="/run/aimilivpn.pid"

start_pre() {
    export DEPLOYMENT_MODE=source PYTHONDONTWRITEBYTECODE=1
    if [ -r /etc/default/aimilivpn ]; then
        set -a
        . /etc/default/aimilivpn
        set +a
    fi
}

depend() {
    need net
    after firewall
}
EOF
    chmod +x /etc/init.d/aimilivpn
    rc-update add aimilivpn default
else
    echo -e "${YELLOW}警告: 未能检测到 systemd 或 OpenRC，请手动管理服务。${PLAIN}"
fi

# 6. Configure global command shortcut "ml"
echo -e "\n${YELLOW}[4/4] 正在创建全局命令快捷接口 'ml'...${PLAIN}"
echo -e "  -> 正在写入管理脚本 /usr/bin/ml ..."
cat > /usr/bin/ml <<'EOF'
#!/usr/bin/env python3
import sys
import os
import socket
import subprocess
import time
import tty
import termios
import shutil

INSTALL_DIR = "/opt/aimilivpn"
sys.path.insert(0, INSTALL_DIR)
import auth_store
import panel_access
import release_utils
from functools import lru_cache

get_panel_host = lru_cache(maxsize=4)(panel_access.public_host)

LOG_FILE = "/opt/aimilivpn/vpngate_data/vpngate.log"

def generate_random_password():
    import secrets
    import string
    chars = string.ascii_letters + string.digits
    while True:
        pwd = "".join(secrets.choice(chars) for _ in range(12))
        if any(c.islower() for c in pwd) and any(c.isupper() for c in pwd) and any(c.isdigit() for c in pwd):
            return pwd

def generate_random_suffix():
    import secrets
    import string
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(12))

def get_app_version():
    try:
        with open(os.path.join(INSTALL_DIR, "VERSION"), "r", encoding="utf-8") as f:
            version = f.read().strip().lstrip("vV")
        return version or "2.1.8"
    except Exception:
        return "2.1.8"

def load_ui_cfg():
    import json
    path = "/opt/aimilivpn/vpngate_data/ui_auth.json"
    cfg = {"host": "127.0.0.1", "port": 8787, "secret_path": ""}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in data.items():
                    cfg[k] = v
        except Exception:
            pass
    return cfg

def save_ui_cfg(cfg):
    import json
    import tempfile
    path = "/opt/aimilivpn/vpngate_data/ui_auth.json"
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(prefix=".ui_auth.", dir=directory)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(temp_path, path)
        return True
    except OSError:
        return False
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def load_state():
    import json
    path = "/opt/aimilivpn/vpngate_data/state.json"
    state = {"active_openvpn_node_id": "", "last_check_message": "", "is_connecting": False}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in data.items():
                    state[k] = v
        except Exception:
            pass
    return state

def get_active_node_info():
    import json
    path = "/opt/aimilivpn/vpngate_data/nodes.json"
    state = load_state()
    active_id = state.get("active_openvpn_node_id")
    if not active_id:
        return None, None
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                nodes = json.load(f)
                for n in nodes:
                    if n.get("id") == active_id:
                        ip = n.get("ip") or n.get("remote_host")
                        loc = n.get("location") or n.get("country") or "未知"
                        return ip, loc
        except Exception:
            pass
    return None, None

def check_port_listening(port):
    for host, family in [("127.0.0.1", socket.AF_INET), ("::1", socket.AF_INET6)]:
        try:
            s = socket.socket(family, socket.SOCK_STREAM)
            s.settimeout(0.2)
            s.connect((host, port))
            s.close()
            return True
        except Exception:
            pass
    return False

def get_service_pid(service_name="aimilivpn.service"):
    try:
        for pid_dir in os.listdir('/proc'):
            if pid_dir.isdigit():
                try:
                    with open(os.path.join('/proc', pid_dir, 'cmdline'), 'r') as f:
                        cmd = f.read()
                        if 'vpngate_manager.py' in cmd:
                            return pid_dir
                except Exception:
                    continue
    except Exception:
        pass
    return None

def check_service_active(service_name="aimilivpn.service"):
    return get_service_pid(service_name) is not None

def check_openvpn_process():
    try:
        for pid_dir in os.listdir('/proc'):
            if pid_dir.isdigit():
                try:
                    with open(os.path.join('/proc', pid_dir, 'cmdline'), 'r') as f:
                        cmd = f.read().replace('\x00', ' ')
                        if 'openvpn' in cmd and ('/opt/aimilivpn/vpngate_data' in cmd or '/opt/aimilivpn/vpngate_data/configs' in cmd):
                            return True
                except Exception:
                    continue
    except Exception:
        pass
    return False

def get_display_width(s):
    import re
    ansi_escape = re.compile(r'\x1b\[[0-9;]*[mGKH]')
    s_clean = ansi_escape.sub('', s)
    width = 0
    for char in s_clean:
        if ord(char) > 127:
            width += 2
        else:
            width += 1
    return width

def format_line(label, value, target_width=26):
    prefix = "  ● "
    w = get_display_width(label)
    padding = " " * max(0, target_width - w)
    return f"{prefix}{label}{padding}:  {value}"

def print_line(text=""):
    print(f"{text}\033[K")

def print_status():
    cfg = load_ui_cfg()
    ui_port = cfg.get("port", 8787)
    secret_path = cfg.get("secret_path", "EJsW2EeBo9lY")
    proxy_port = cfg.get("proxy_port", 7928)
    state = load_state()
    is_connecting = state.get("is_connecting", False)
    
    gateway_ok = check_port_listening(proxy_port)
    service_ok = check_service_active("aimilivpn.service")
    openvpn_ok = check_openvpn_process()
    pid = get_service_pid("aimilivpn.service")
    
    active_ip, active_loc = get_active_node_info()
    latency = state.get("active_node_latency", "测试中...") if active_ip else "无活动连接"
    
    green = "\033[1;32m"
    red = "\033[1;31m"
    reset = "\033[0m"
    bold = "\033[1m"
    yellow = "\033[1;33m"
    
    backend_status = f"{green}[已激活] (PID: {pid}){reset}" if (service_ok and pid) else f"{red}[未启动]{reset}"
    
    if is_connecting:
        gateway_status = f"{yellow}[切换中...]{reset}"
        openvpn_status = f"{yellow}[{state.get('active_node_latency') or '连接中'}...]{reset}"
    else:
        gateway_status = f"{green}[已激活]{reset}" if gateway_ok else f"{red}[未启动]{reset}"
        openvpn_status = f"{green}[已连接]{reset}" if openvpn_ok else f"{red}[未连接]{reset}"
    
    print_line("=======================================================")
    print_line(f"               {bold}AimiliVPN 管理终端 v{get_app_version()}{reset}                ")
    print_line("=======================================================")
    print_line("【核心服务状态】")
    print_line(format_line(f"代理网关 (Port {proxy_port})", gateway_status))
    print_line(format_line(f"管理后台 (Port {ui_port})", backend_status))
    print_line(format_line("连接核心 (OpenVPN)", openvpn_status))
    
    login_ip = get_panel_host(cfg.get("host", "0.0.0.0"))
    if ":" in login_ip:
        login_ip = f"[{login_ip}]"
    print_line(format_line("网页登录地址", f"{yellow}http://{login_ip}:{ui_port}/{secret_path}/{reset}"))
    print_line(format_line("网页管理账号", cfg.get("username", "未配置")))
    print_line(format_line("网页管理密码", "已设置" if (cfg.get("password_hash") or cfg.get("password")) else "未配置"))
    print_line()
    print_line("【活动节点状态】")
    if is_connecting:
        connecting_msg = state.get('last_check_message') or '正在建立加密隧道并验证路由规则...'
        print_line(format_line("节点状态", f"{yellow}{connecting_msg}{reset}"))
    elif active_ip:
        proxy_ip = state.get("proxy_ip", "-")
        proxy_latency = state.get("proxy_latency_ms", 0)
        proxy_ok = state.get("proxy_ok", False)
        
        print_line(format_line("节点 IP (入口)", active_ip))
        print_line(format_line("节点地区", active_loc))
        print_line(format_line("节点延迟 (直连测试)", latency))
        if proxy_ok and proxy_ip and proxy_ip != "-":
            print_line(format_line("出口 IP (出站)", proxy_ip))
            print_line(format_line("本地代理延迟", f"{proxy_latency} ms" if proxy_latency else "检测中..."))
        else:
            proxy_err = state.get("proxy_error") or "检测中/未就绪"
            print_line(format_line("出口 IP (出站)", f"{red}[不可用 - {proxy_err}]{reset}"))
    else:
        print_line(format_line("节点状态", "无活动连接"))
    print_line()
    local_proxy = state.get("local_proxy", f"http://127.0.0.1:{proxy_port}")
    import urllib.parse
    try:
        parsed = urllib.parse.urlsplit(local_proxy)
        proxy_host = parsed.hostname or "127.0.0.1"
        proxy_port = parsed.port or proxy_port
    except Exception:
        proxy_host = "127.0.0.1"
        proxy_port = proxy_port
    
    if proxy_host == "::":
        proxy_addr = "127.0.0.1"
    elif ":" in proxy_host:
        proxy_addr = f"[{proxy_host}]"
    else:
        proxy_addr = proxy_host

    print_line("【使用方法】")
    print_line(f"  export http_proxy=http://{proxy_addr}:{proxy_port}")
    print_line(f"  export https_proxy=http://{proxy_addr}:{proxy_port}")
    print_line(f"  # 也可用于 SOCKS5: socks5://{proxy_addr}:{proxy_port}")
    print_line("=======================================================")

def run_service_cmd(cmd):
    if shutil.which("systemctl"):
        subprocess.run(["systemctl", cmd, "aimilivpn.service"])
    elif shutil.which("rc-service"):
        subprocess.run(["rc-service", "aimilivpn", cmd])
    else:
        print("未检测到支持的服务管理器 (systemd/OpenRC)")

def start_service():
    print("正在启动 AimiliVPN 服务...", flush=True)
    run_service_cmd("start")
    print("已发送启动指令。")
    time.sleep(1)

def stop_service():
    print("正在停止 AimiliVPN 服务...", flush=True)
    run_service_cmd("stop")
    print("已发送停止指令。")
    time.sleep(1)

def restart_service():
    print("正在重启 AimiliVPN 服务...", flush=True)
    run_service_cmd("restart")
    print("已发送重启指令。")
    time.sleep(1)

def show_logs():
    print("正在查看 AimiliVPN 日志 (按 Ctrl+C 退出)...", flush=True)
    if os.path.exists(LOG_FILE):
        try:
            subprocess.run(["tail", "-F", "-n", "50", LOG_FILE])
        except KeyboardInterrupt:
            pass
    else:
        print(f"日志文件不存在: {LOG_FILE}")
        time.sleep(2)

def update_service(tag=None):
    if os.path.exists(os.path.join(INSTALL_DIR, ".local_dev")):
        print("本地开发模式已启用。请在可信工作区手动更新源码。")
        raise SystemExit(1)
    try:
        release = release_utils.resolve_release(tag)
        # An explicit tag also allows a deliberate reinstall or rollback.
        if tag is None and release_utils.version_key(release.tag) <= release_utils.version_key("v" + get_app_version()):
            print(f"当前版本 v{get_app_version()}，最新发行版 {release.tag}。")
            return
        if os.environ.get("AIMILIVPN_NONINTERACTIVE") != "1":
            confirm = input(f"安装发行版 {release.tag} 并重启服务？(y/N): ").strip().lower()
            if confirm not in {"y", "yes"}:
                print("已取消更新。")
                return
        release_utils.install_release(release)
        print("更新已完成！")
    except Exception as exc:
        print(f"更新失败: {exc}", file=sys.stderr)
        raise SystemExit(1)

def uninstall_service():
    confirm = input("确定要完全卸载 AimiliVPN 吗？(y/N): ")
    if confirm.lower() == 'y':
        print("正在完全卸载 AimiliVPN...", flush=True)
        stop_service()
        if shutil.which("systemctl"):
            subprocess.run(["systemctl", "disable", "aimilivpn.service"])
            for unit_path in ("/lib/systemd/system/aimilivpn.service", "/etc/systemd/system/aimilivpn.service"):
                try:
                    os.unlink(unit_path)
                except FileNotFoundError:
                    pass
            subprocess.run(["systemctl", "daemon-reload"], check=False)
        elif shutil.which("rc-service"):
            subprocess.run(["rc-update", "del", "aimilivpn"])
            try:
                os.unlink("/etc/init.d/aimilivpn")
            except Exception:
                pass
        try:
            os.unlink("/usr/bin/ml")
        except FileNotFoundError:
            pass
        try:
            os.unlink("/etc/sysctl.d/99-aimilivpn.conf")  # Legacy AimiliVPN file.
        except FileNotFoundError:
            pass
        if os.path.realpath(INSTALL_DIR) == "/opt/aimilivpn" and os.path.isdir(INSTALL_DIR):
            shutil.rmtree(INSTALL_DIR)
        print("AimiliVPN 已卸载！")
        sys.exit(0)
    else:
        print("已取消卸载。")
        time.sleep(1)

def ask_restart():
    ans = input("配置已保存。是否立即重启服务生效？(Y/n): ").strip().lower()
    if ans in ('', 'y', 'yes'):
        print("正在重启 AimiliVPN 服务...", flush=True)
        restart_service()
        print("服务已重启。")
        time.sleep(1.5)

def configure_web():
    cfg = load_ui_cfg()
    while True:
        print("\033[H\033[J", end="")
        print("=======================================================")
        print("               网页绑定与地址后缀配置                  ")
        print("=======================================================")
        print(f"  [1] 切换绑定地址 (当前: {cfg.get('host', '0.0.0.0')})")
        print(f"  [2] 随机重置安全后缀 (当前: {cfg.get('secret_path', '')})")
        print("  [3] 返回主菜单")
        print("=======================================================")
        print("请直接输入数字键 [1-3] 快速执行：", end="", flush=True)
        
        key = getch()
        if key == '1':
            print("\033[H\033[J", end="")
            print("选择网页登录绑定地址：")
            print("  1. 仅允许本地 IPv4 登录 (127.0.0.1 - 更安全)")
            print("  2. 允许 IPv4 公网登录 (0.0.0.0)")
            print("  3. 允许 IPv4 & IPv6 双栈公网登录 (:: - 推荐)")
            print("  4. 仅允许本地 IPv6 登录 (::1)")
            sel = input("请选择 (1/2/3/4, 默认3): ").strip()
            if sel == '1':
                cfg['host'] = "127.0.0.1"
            elif sel == '2':
                cfg['host'] = "0.0.0.0"
            elif sel == '4':
                cfg['host'] = "::1"
            else:
                cfg['host'] = "::"
            save_ui_cfg(cfg)
            print(f"绑定地址已更新为: {cfg['host']}")
            ask_restart()
            break
        elif key == '2':
            print("\033[H\033[J", end="")
            new_path = generate_random_suffix()
            cfg['secret_path'] = new_path
            save_ui_cfg(cfg)
            print("安全登录后缀已随机重置成功！")
            print(f"您的全新安全登录后缀为: {new_path}")
            display_host = cfg['host']
            if ":" in display_host:
                display_host = f"[{display_host}]"
            print(f"新的访问路径为: http://{display_host}:{cfg['port']}/{new_path}/")
            ask_restart()
            break
        elif key == '3' or key == 'q' or key == '\x03':
            break

def configure_port():
    cfg = load_ui_cfg()
    while True:
        print("\033[H\033[J", end="")
        print("=======================================================")
        print("                      端口配置菜单                     ")
        print("=======================================================")
        print(f"1) 网页管理端口: {cfg.get('port', 8787)}")
        print(f"2) 代理出站端口: {cfg.get('proxy_port', 7928)}")
        print("3) 返回主菜单")
        print("-------------------------------------------------------")
        key = input("请选择操作 (1-3): ").strip()
        if key == '1':
            try:
                val = input("请输入新的网页管理端口 (1-65535, 按回车取消): ").strip()
                if val:
                    port = int(val)
                    if 1 <= port <= 65535:
                        if port == int(cfg.get('proxy_port', 7928)):
                            print("错误: 网页管理端口不能与代理出站端口相同。")
                            time.sleep(2)
                            continue
                        cfg['port'] = port
                        save_ui_cfg(cfg)
                        print(f"网页管理端口已更新为: {port}")
                        ask_restart()
                    else:
                        print("错误: 端口范围必须在 1 至 65535 之间。")
                        time.sleep(2)
            except ValueError:
                print("错误: 输入必须是数字。")
                time.sleep(2)
        elif key == '2':
            try:
                val = input("请输入新的代理出站端口 (1024-65535, 按回车取消): ").strip()
                if val:
                    port = int(val)
                    if 1024 <= port <= 65535:
                        if port == int(cfg.get('port', 8787)):
                            print("错误: 代理出站端口不能与网页管理端口相同。")
                            time.sleep(2)
                            continue
                        cfg['proxy_port'] = port
                        save_ui_cfg(cfg)
                        print(f"代理出站端口已更新为: {port}")
                        ask_restart()
                    else:
                        print("错误: 端口范围必须在 1024 至 65535 之间。")
                        time.sleep(2)
            except ValueError:
                print("错误: 输入必须是数字。")
                time.sleep(2)
        elif key == '3' or key == 'q' or key == '\x03':
            break

def configure_credentials():
    bootstrap = os.path.join(INSTALL_DIR, "vpngate_data", "ui_bootstrap.json")
    cfg = load_ui_cfg()
    while True:
        print("\033[H\033[J", end="")
        print("=======================================================")
        print("                    管理账号密码管理                   ")
        print("=======================================================")
        curr_uname = cfg.get('username', '未配置')
        print(f"当前管理账号: {curr_uname}")
        print("  [1] 自定义修改账号密码")
        print("  [2] 随机重置安全密码")
        print("  [3] 返回主菜单")
        print("=======================================================")
        print("请直接输入数字键 [1-3] 快速执行：", end="", flush=True)
        
        key = getch()
        if key == '1':
            print("\033[H\033[J", end="")
            new_uname = input(f"请输入新管理账号 (回车默认 {curr_uname}): ").strip()
            if not new_uname:
                new_uname = curr_uname
            new_pwd = __import__("getpass").getpass("请输入新管理密码 (不能为空): ")
            if not new_pwd:
                print("错误: 密码不能为空！")
                time.sleep(2)
                continue
            cfg['username'] = new_uname
            auth_store.set_password(cfg, new_pwd)
            if not save_ui_cfg(cfg):
                print("保存管理凭据失败。")
                input("\n按任意键返回菜单...")
                continue
            os.unlink(bootstrap) if os.path.exists(bootstrap) else None
            print("账号密码修改成功！")
            print(f"您的新管理账号: {new_uname}")
            print(f"您的新管理密码: {new_pwd}")
            input("\n按任意键返回菜单...")
        elif key == '2':
            print("\033[H\033[J", end="")
            new_pwd = generate_random_password()
            auth_store.set_password(cfg, new_pwd)
            if not save_ui_cfg(cfg):
                print("保存管理凭据失败。")
                input("\n按任意键返回菜单...")
                continue
            os.unlink(bootstrap) if os.path.exists(bootstrap) else None
            print("密码随机重置成功！")
            print(f"您的全新12位安全密码为: {new_pwd}")
            print("密码已保存在本地，不需要重启服务，刷新浏览器即可登录。")
            input("\n按任意键返回菜单...")
        elif key == '3' or key == 'q' or key == '\x03':
            break

def getch():
    fd = sys.stdin.fileno()
    try:
        old_settings = termios.tcgetattr(fd)
    except termios.error:
        ch = sys.stdin.read(1)
        return ch if ch else "q"
    try:
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch if ch else "q"

def main():
    if os.geteuid() != 0:
        print("错误: 必须以 root 权限运行此命令。")
        sys.exit(1)
        
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "start":
            start_service()
        elif cmd == "stop":
            stop_service()
        elif cmd == "restart":
            restart_service()
        elif cmd == "status":
            print("\033[?1049h\033[?25l\033[H\033[J", end="", flush=True)
            try:
                while True:
                    print("\033[H", end="")
                    print_status()
                    print_line("\n\033[1;33m提示: 当前为静态页面。按 [回车键/Enter] 手动刷新状态，按 [q] 或 [Ctrl+C] 退出...\033[0m")
                    print("\033[J", end="", flush=True)
                    
                    key = getch()
                    if key in ('q', 'Q', '\x03'):
                        break
                    if key in ('\r', '\n', '\x0a', '\x0d'):
                        continue
            except KeyboardInterrupt:
                pass
            finally:
                print("\033[?1049l\033[?25h", end="", flush=True)
        elif cmd == "logs":
            show_logs()
        elif cmd == "update":
            if len(sys.argv) > 3:
                print("用法: ml update [vX.Y.Z]", file=sys.stderr)
                raise SystemExit(1)
            update_service(sys.argv[2] if len(sys.argv) == 3 else None)
        elif cmd == "uninstall":
            uninstall_service()
        elif cmd == "web":
            configure_web()
        elif cmd == "port":
            configure_port()
        elif cmd == "password":
            configure_credentials()
        else:
            print("未知命令。可用命令: start, stop, restart, status, logs, update, uninstall, web, port, password")
        sys.exit(0)
        
    options = {
        '1': ("启动服务 (ml start)", start_service),
        '2': ("停止服务 (ml stop)", stop_service),
        '3': ("重启服务 (ml restart)", restart_service),
        '4': ("日志监控 (ml logs)", show_logs),
        '5': ("网页配置 (ml web)", configure_web),
        '6': ("端口配置 (ml port)", configure_port),
        '7': ("账号密码 (ml password)", configure_credentials),
        '8': ("一键更新 (ml update)", update_service),
        '9': ("完全卸载 (ml uninstall)", uninstall_service),
        '0': ("退出终端", None)
    }
    
    # Enter alternate buffer and hide cursor
    print("\033[?1049h\033[?25l\033[H\033[J", end="", flush=True)
    try:
        need_redraw = True
        while True:
            if need_redraw:
                print("\033[H", end="")
                print_status()
                
                bold = "\033[1m"
                reset = "\033[0m"
                green = "\033[1;32m"
                
                print_line(f"【{bold}终端指令菜单栏{reset}】")
                for key in sorted(options.keys()):
                    if key == '0':
                        continue
                    name, _ = options[key]
                    print_line(f"  {green}[{key}]{reset} {name}")
                print_line(f"  {green}[0]{reset} {options['0'][0]}")
                print_line("=======================================================")
                print_line("提示: 当前为静态页面。按 [回车键/Enter] 手动刷新状态。")
                print("请直接输入数字键 [0-9] 快速选择执行：\033[K", end="", flush=True)
                print("\033[J", end="", flush=True)
                need_redraw = False
                
            try:
                key = getch()
            except KeyboardInterrupt:
                break
                
            if key == '\x03' or key == 'q' or key == 'Q':
                break
                
            if key == '0':
                break
                
            if key in ('\r', '\n', '\x0a', '\x0d'):
                need_redraw = True
                continue
                
            if key in options:
                name, func = options[key]
                if func is None:
                    break
                    
                # Temporarily restore normal terminal scrollback and show cursor
                print("\033[?1049l\033[?25h", end="", flush=True)
                print(f"正在执行: {name}...\n")
                
                try:
                    func()
                except Exception as e:
                    print(f"执行出错: {e}")
                    
                if func not in (start_service, stop_service, restart_service,
                                configure_web, configure_port, configure_credentials, show_logs, update_service):
                    input("\n操作已完成，按回车键返回主菜单...")
                    
                # Re-enter alternate buffer and hide cursor
                print("\033[?1049h\033[?25l\033[H\033[J", end="", flush=True)
                need_redraw = True
    finally:
        # Exit alternate buffer and show cursor on exit
        print("\033[?1049l\033[?25h", end="", flush=True)

if __name__ == "__main__":
    main()
EOF
chmod +x /usr/bin/ml

# The service creates the same credentials for both installation modes.
AUTH_FILE="${INSTALL_DIR}/vpngate_data/ui_auth.json"
install -d -m 700 "${INSTALL_DIR}/vpngate_data"
if [ -f "$AUTH_FILE" ]; then chmod 600 "$AUTH_FILE"; fi

# 8. Start service
echo -e "\n正在启动 AimiliVPN 服务并初始化网络..."
service_status=()
if command -v systemctl >/dev/null 2>&1; then
    systemctl restart aimilivpn.service
    service_status=(systemctl is-active --quiet aimilivpn.service)
elif command -v rc-service >/dev/null 2>&1; then
    rc-service aimilivpn restart
    service_status=(rc-service aimilivpn status)
fi

python3 "$INSTALL_DIR/panel_access.py" health --data-dir "$INSTALL_DIR/vpngate_data" --wait 45
if ((${#service_status[@]})) && ! "${service_status[@]}" >/dev/null; then
    echo 'AimiliVPN 服务未保持运行，请检查服务日志。' >&2
    exit 1
fi
echo '管理服务已启动。'
python3 "$INSTALL_DIR/panel_access.py" summary --data-dir "$INSTALL_DIR/vpngate_data"
echo '管理命令  ml'
