#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import tarfile
import tempfile
from pathlib import Path

RELEASE_FILES = [
    ".dockerignore",
    "VERSION",
    "README.md",
    "RELEASE_NOTES.md",
    "LICENSE",
    "install.sh",
    "vpngate_manager.py",
    "vpn_utils.py",
    "proxy_server.py",
    "snapshot_utils.py",
    "auth_store.py",
    "release_utils.py",
    "Dockerfile",
    "compose.yaml",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_installers(root: Path, output_dir: Path, version: str) -> None:
    if not re.fullmatch(r"[0-9]{1,9}\.[0-9]{1,9}\.[0-9]{1,9}", version):
        raise ValueError("安装脚本版本必须采用 X.Y.Z 格式")
    compose = (root / "compose.yaml").read_text(encoding="utf-8").rstrip("\n")
    compose, image_count = re.subn(
        r"(?m)^    image: ghcr\.io/openmili/aimili-vpngate:[^\s]+$",
        f"    image: ghcr.io/openmili/aimili-vpngate:{version}",
        compose,
    )
    compose = re.sub(r"(?m)^    build:\n(?: {6}[^\n]*\n)+", "", compose)
    if image_count != 1 or "AIMILIVPN_COMPOSE" in compose.splitlines() or "    build:" in compose.splitlines():
        raise ValueError("Compose 配置无法生成固定版本的 Docker 安装脚本")

    source = (root / "install.sh").read_text(encoding="utf-8")
    channel = "\nbootstrap_release=latest\n"
    if source.count(channel) != 1:
        raise ValueError("无法为独立源码安装脚本锁定发行版")
    docker = (root / "scripts" / "install-docker.sh.in").read_text(encoding="utf-8")
    if docker.count("@COMPOSE_YAML@") != 1 or docker.count("@RELEASE_TAG@") != 1:
        raise ValueError("Docker 安装模板中缺少发行版或 Compose 配置")

    output_dir.mkdir(parents=True, exist_ok=True)
    source = source.replace(channel, f"\nbootstrap_release=v{version}\n")
    checksum = hashlib.sha256((compose + "\n").encode("utf-8")).hexdigest()
    managed_compose = f"# AimiliVPN managed compose {checksum}\n{compose}"
    docker = docker.replace("@RELEASE_TAG@", f"v{version}").replace("@COMPOSE_YAML@", managed_compose)
    (output_dir / "install-source.sh").write_bytes(source.encode("utf-8"))
    (output_dir / "install-docker.sh").write_bytes(docker.encode("utf-8"))


def build_archive(root: Path, output_dir: Path) -> Path:
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[0-9]{1,9}\.[0-9]{1,9}\.[0-9]{1,9}", version):
        raise ValueError("VERSION 必须采用 X.Y.Z 格式")

    missing = [name for name in RELEASE_FILES if not (root / name).is_file()]
    if missing:
        raise FileNotFoundError(f"发行文件缺失: {', '.join(missing)}")
    if not (root / "mirror").is_dir():
        raise FileNotFoundError("发行文件缺失: mirror")

    output_dir.mkdir(parents=True, exist_ok=True)
    for stale_archive in output_dir.glob("aimilivpn-v*-linux-*.tar.gz"):
        stale_archive.unlink()
    checksum_path = output_dir / "sha256sums.txt"
    checksum_path.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory(prefix="aimilivpn-release-") as temp_name:
        temp_root = Path(temp_name)
        package_name = f"aimilivpn-v{version}-linux-source"
        package_root = temp_root / package_name
        package_root.mkdir()

        for name in RELEASE_FILES:
            target = package_root / name
            shutil.copy2(root / name, target)
            if name == "install.sh":
                target.write_bytes(target.read_bytes().replace(b"\r\n", b"\n"))
        shutil.copytree(root / "mirror", package_root / "mirror")

        archive_path = output_dir / f"{package_name}.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(package_root, arcname=package_name)

    checksum_lines = [f"{sha256(archive_path)}  {archive_path.name}"]
    checksum_path.write_bytes(("\n".join(checksum_lines) + "\n").encode("ascii"))
    build_installers(root, output_dir, version)
    return archive_path


def main() -> int:
    parser = argparse.ArgumentParser(description="构建 AimiliVPN Linux 通用 Python 源码发行包")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path, default=Path("dist"))
    args = parser.parse_args()

    archive = build_archive(args.root.resolve(), args.output_dir.resolve())
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
