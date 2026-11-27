"""Fetch and stage an official source Release before starting its installer."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request


_RELEASES_URL = "https://github.com/OpenMili/aimili-vpngate/releases"
_TAG = r"v[0-9]{1,9}\.[0-9]{1,9}\.[0-9]{1,9}"
_MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
_REQUIRED_FILES = {
    "VERSION", "README.md", "LICENSE", "install.sh", "release_utils.py", "auth_store.py",
    "vpngate_manager.py", "vpn_utils.py", "proxy_server.py", "snapshot_utils.py",
    "mirror/vpngate.csv", "mirror/vpngate.meta.json",
}


@dataclass(frozen=True)
class Release:
    tag: str
    sha256: str

    @property
    def folder(self) -> str:
        return f"aimilivpn-{self.tag}-linux-source"


class _HTTPSRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith("https://"):
            raise ValueError("Release 下载被重定向到了非 HTTPS 地址")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download(url: str, limit: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "AimiliVPN Release Installer"})
    opener = urllib.request.build_opener(_HTTPSRedirects())
    with opener.open(request, timeout=30) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Release 下载超过大小限制")
    return data


def version_key(tag: str) -> tuple[int, int, int]:
    if not re.fullmatch(_TAG, tag):
        raise ValueError("发行版标签必须采用 vX.Y.Z 格式")
    major, minor, patch = (int(part) for part in tag[1:].split("."))
    return major, minor, patch


def resolve_release(tag: str | None = None) -> Release:
    if tag is not None:
        version_key(tag)
    channel = f"download/{tag}" if tag else "latest/download"
    manifest = _download(f"{_RELEASES_URL}/{channel}/sha256sums.txt", 4096).decode("ascii")
    match = re.fullmatch(rf"([a-fA-F0-9]{{64}})[ \t]+\*?aimilivpn-({_TAG})-linux-source\.tar\.gz", manifest.strip())
    if not match or (tag and match[2] != tag):
        raise ValueError("Release 校验清单与请求版本不一致")
    return Release(match[2], match[1].lower())


def stage_release(release: Release, destination: Path) -> Path:
    """Use an empty private staging directory and extract only regular files."""
    version_key(release.tag)
    name = release.folder
    data = _download(f"{_RELEASES_URL}/download/{release.tag}/{name}.tar.gz", _MAX_ARCHIVE_BYTES)
    if hashlib.sha256(data).hexdigest() != release.sha256:
        raise ValueError("Release SHA-256 校验失败")
    archive = destination / "release.tar.gz"
    archive.write_bytes(data)
    files: set[str] = set()
    total_size = 0
    with tarfile.open(archive, "r:gz") as package:
        for index, entry in enumerate(package):
            path = PurePosixPath(entry.name)
            if index >= 64 or not path.parts or path.parts[0] != name or ".." in path.parts or "\\" in entry.name:
                raise ValueError("Release 包包含无效文件路径或文件数量过多")
            target = destination.joinpath(*path.parts)
            if entry.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not entry.isfile() or len(path.parts) < 2 or entry.size < 0:
                raise ValueError("Release 包包含非普通文件")
            total_size += entry.size
            if total_size > _MAX_ARCHIVE_BYTES:
                raise ValueError("Release 解压后超过大小限制")
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output, package.extractfile(entry) as source:
                shutil.copyfileobj(source, output)
            files.add(PurePosixPath(*path.parts[1:]).as_posix())
    if not _REQUIRED_FILES <= files:
        raise ValueError("Release 缺少完整安装文件，请选择包含新安装器的发行版")
    root = destination / name
    if (root / "VERSION").read_text(encoding="utf-8").strip() != release.tag[1:]:
        raise ValueError("Release 标签与包内 VERSION 文件不一致")
    return root


def install_release(release: Release) -> None:
    with tempfile.TemporaryDirectory(prefix="aimilivpn-update-") as temp:
        source = stage_release(release, Path(temp))
        subprocess.run(["bash", str(source / "install.sh")], cwd=source, check=True)
