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
