"""Blocking, stdlib-only installer for official Linux x86-64 XMRig releases.

Call install_latest from a worker thread. Validation failures raise ValueError;
filesystem and network errors propagate (including FileExistsError).
"""

import gzip
import hashlib
import io
import json
import os
import platform
import re
import stat
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen

_API = "https://api.github.com/repos/xmrig/xmrig/releases/latest"
_LIMIT = 64 * 1024 * 1024
_API_LIMIT = 2 * 1024 * 1024
_TIMEOUT = 30
_USER_AGENT = "XMRiGUI-Linux/miner-installer"


def user_miner_path() -> Path:
    """Return the per-user miner destination, respecting absolute XDG_DATA_HOME."""
    data_home = os.environ.get("XDG_DATA_HOME")
    root = (
        Path(data_home)
        if data_home and Path(data_home).is_absolute()
        else Path.home() / ".local/share"
    )
    return root / "xmrigui/miner/xmrig"


def discover_miner(base: Path) -> Path | None:
    """Find the first executable regular miner in the documented search order."""
    for path in (
        Path("/opt/xmrigui/xmrig"),
        base / "xmrig",
        base / "miner/xmrig",
        user_miner_path(),
    ):
        try:
            if stat.S_ISREG(path.stat().st_mode) and os.access(path, os.X_OK):
                return path
        except OSError:
            continue
    return None


def _download(url: str, limit: int) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "application/vnd.github+json"
            if url == _API
            else "application/octet-stream",
        },
    )
    with urlopen(request, timeout=_TIMEOUT) as response:
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = response.read(min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
    if len(data) > limit:
        raise ValueError("Download exceeds size limit")
    return data


def _binary(archive: bytes) -> bytes:
    # Bound decompression as well as the compressed download. Allow tar overhead.
    with gzip.GzipFile(fileobj=io.BytesIO(archive)) as compressed:
        unpacked = compressed.read(_LIMIT + 1024 * 1024 + 1)
    if len(unpacked) > _LIMIT + 1024 * 1024:
        raise ValueError("Unpacked archive exceeds size limit")
    binary = None
    with tarfile.open(fileobj=io.BytesIO(unpacked), mode="r:") as tar:
        for member in tar:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or "\\" in member.name:
                raise ValueError("Unsafe archive path")
            if not (member.isdir() or member.isreg()):
                raise ValueError("Archive links and special members are forbidden")
            if path.name != "xmrig":
                continue
            if (
                not member.isreg()
                or not 0 < member.size <= _LIMIT
                or binary is not None
            ):
                raise ValueError("Expected exactly one regular xmrig binary")
            source = tar.extractfile(member)
            if source is None:
                raise ValueError("Missing binary data")
            with source:
                binary = source.read(_LIMIT + 1)
            if len(binary) != member.size:
                raise ValueError("Truncated binary")
    if binary is None:
        raise ValueError("Archive contains no xmrig binary")
    # ELF64, little-endian, current ELF version, x86-64, executable or PIE.
    if (
        len(binary) < 64
        or binary[:7] != b"\x7fELF\x02\x01\x01"
        or int.from_bytes(binary[16:18], "little") not in (2, 3)
        or binary[18:20] != b"\x3e\x00"
        or binary[20:24] != b"\x01\x00\x00\x00"
    ):
        raise ValueError("Miner is not a Linux x86-64 ELF binary")
    return binary


def install_latest(destination: Path) -> str:
    """Install latest stable official static x64 release; return its vX.Y.Z tag.

    Never replaces an existing path, even if another installer wins a race.
    No downloaded code is executed. Network operations use bounded reads and
    socket timeouts; callers must run this blocking function off the UI thread.
    """
    if platform.system() != "Linux" or platform.machine().lower() not in (
        "x86_64",
        "amd64",
    ):
        raise ValueError("Only Linux x86_64/amd64 is supported")
    destination = Path(destination)
    if os.path.lexists(destination):
        raise FileExistsError(destination)
    release = json.loads(_download(_API, _API_LIMIT))
    if not isinstance(release, dict):
        raise ValueError("Invalid release metadata")
    tag = release.get("tag_name")
    if (
        not isinstance(tag, str)
        or not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag)
        or release.get("draft") is not False
        or release.get("prerelease") is not False
    ):
        raise ValueError("Expected a stable vX.Y.Z release")
    name = f"xmrig-{tag[1:]}-linux-static-x64.tar.gz"
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise ValueError("Missing release assets")
    matches = [
        asset
        for asset in assets
        if isinstance(asset, dict) and asset.get("name") == name
    ]
    if len(matches) != 1:
        raise ValueError("Expected exactly one official static x64 asset")
    asset = matches[0]
    size, digest = asset.get("size"), asset.get("digest")
    if type(size) is not int or not 0 < size <= _LIMIT:
        raise ValueError("Invalid asset size")
    if not isinstance(digest, str) or not re.fullmatch(
        r"sha256:[0-9a-fA-F]{64}", digest
    ):
        raise ValueError("A SHA-256 asset digest is required")
    archive = _download(
        f"https://github.com/xmrig/xmrig/releases/download/{tag}/{name}", size
    )
    if (
        len(archive) != size
        or hashlib.sha256(archive).hexdigest() != digest[7:].lower()
    ):
        raise ValueError("Asset size or SHA-256 verification failed")
    binary = _binary(archive)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".xmrig-", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as staged:
            staged.write(binary)
            staged.flush()
            os.fchmod(staged.fileno(), 0o755)
            os.fsync(staged.fileno())
        os.link(temporary, destination)
    finally:
        os.unlink(temporary)
    return tag
