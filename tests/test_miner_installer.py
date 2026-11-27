import hashlib
import io
import json
import os
import stat
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import miner_installer as installer

TAG = "v6.24.0"
NAME = "xmrig-6.24.0-linux-static-x64.tar.gz"
API = "https://api.github.com/repos/xmrig/xmrig/releases/latest"
ASSET = f"https://github.com/xmrig/xmrig/releases/download/{TAG}/{NAME}"
BINARY = (
    b"\x7fELF\x02\x01\x01" + bytes(9) + b"\x02\x00\x3e\x00\x01\x00\x00\x00" + bytes(40)
)


def make_archive(*extra, binary=BINARY):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as tar:
        for name, content, kind in (("release/xmrig", binary, tarfile.REGTYPE), *extra):
            member = tarfile.TarInfo(name)
            member.size = len(content)
            member.type = kind
            if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                member.linkname = "release/xmrig"
            tar.addfile(member, io.BytesIO(content))
    return stream.getvalue()


class MinerInstallerTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.destination = self.root / "miner/xmrig"
        self.enterContext(
            patch.object(installer.platform, "system", return_value="Linux")
        )
        self.machine = self.enterContext(
            patch.object(installer.platform, "machine", return_value="x86_64")
        )
        self.urlopen = self.enterContext(patch.object(installer, "urlopen"))

    def fixture(self, archive, *, asset_fields=None, release_fields=None):
        asset = dict(
            name=NAME,
            size=len(archive),
            digest="sha256:" + hashlib.sha256(archive).hexdigest(),
            browser_download_url="https://invalid.example/ignored",
        )
        asset.update(asset_fields or {})
        release = dict(tag_name=TAG, draft=False, prerelease=False, assets=[asset])
        release.update(release_fields or {})
        self.urlopen.reset_mock()
        self.urlopen.side_effect = [
            io.BytesIO(json.dumps(release).encode()),
            io.BytesIO(archive),
        ]

    def test_installs_official_asset(self):
        self.fixture(make_archive(("release/SHA256SUMS", b"ignored", tarfile.REGTYPE)))
        self.assertEqual(installer.install_latest(self.destination), TAG)
        self.assertEqual(self.destination.read_bytes(), BINARY)
        self.assertEqual(stat.S_IMODE(self.destination.stat().st_mode), 0o755)
        self.assertEqual(list(self.destination.parent.iterdir()), [self.destination])
        self.assertEqual(
            [call.args[0].full_url for call in self.urlopen.call_args_list],
            [API, ASSET],
        )
        for call in self.urlopen.call_args_list:
            self.assertTrue(call.args[0].get_header("User-agent"))
            self.assertGreater(call.kwargs["timeout"], 0)

    def test_hash_failure_before_tar_processing(self):
        self.fixture(make_archive(), asset_fields={"digest": "sha256:" + "0" * 64})
        with patch.object(installer.tarfile, "open") as tar_open:
            with self.assertRaisesRegex(ValueError, "SHA-256 verification"):
                installer.install_latest(self.destination)
            tar_open.assert_not_called()
        self.assertFalse(self.destination.parent.exists())

    def test_invalid_release_metadata(self):
        for fields in (
            {"tag_name": "v6.24.0-rc1"},
            {"prerelease": True},
            {"draft": True},
            {"assets": []},
        ):
            with self.subTest(fields=fields):
                self.fixture(make_archive(), release_fields=fields)
                with self.assertRaises(ValueError):
                    installer.install_latest(self.destination)
                self.assertEqual(self.urlopen.call_count, 1)

    def test_invalid_asset_metadata(self):
        for fields in (
            {"digest": None},
            {"size": 0},
            {"size": True},
            {"size": 64 * 1024**2 + 1},
        ):
            with self.subTest(fields=fields):
                self.fixture(make_archive(), asset_fields=fields)
                with self.assertRaises(ValueError):
                    installer.install_latest(self.destination)
                self.assertEqual(self.urlopen.call_count, 1)

    def test_size_mismatch(self):
        archive = make_archive()
        for size in (len(archive) - 1, len(archive) + 1):
            with self.subTest(size=size):
                self.fixture(archive, asset_fields={"size": size})
                with self.assertRaises(ValueError):
                    installer.install_latest(self.destination)
                self.assertFalse(self.destination.parent.exists())

    def test_unsafe_members_rejected_even_after_valid_binary(self):
        for name, kind in (
            ("../escape", tarfile.REGTYPE),
            ("/escape", tarfile.REGTYPE),
            ("symlink", tarfile.SYMTYPE),
            ("hardlink", tarfile.LNKTYPE),
            ("fifo", tarfile.FIFOTYPE),
            ("duplicate/xmrig", tarfile.REGTYPE),
        ):
            with self.subTest(name=name):
                self.fixture(
                    make_archive(
                        (name, BINARY if kind == tarfile.REGTYPE else b"", kind)
                    )
                )
                with self.assertRaises(ValueError):
                    installer.install_latest(self.destination)
                self.assertFalse(self.destination.parent.exists())

    def test_invalid_elf(self):
        self.fixture(make_archive(binary=BINARY[:18] + b"\xb7\x00" + BINARY[20:]))
        with self.assertRaisesRegex(ValueError, "ELF"):
            installer.install_latest(self.destination)

    def test_unsupported_platform(self):
        for system, machine in (("Linux", "aarch64"), ("Windows", "amd64")):
            with self.subTest(system=system, machine=machine):
                self.machine.return_value = machine
                installer.platform.system.return_value = system
                with self.assertRaisesRegex(ValueError, "Only Linux x86_64/amd64"):
                    installer.install_latest(self.destination)
        self.urlopen.assert_not_called()

    def test_existing_file_and_dangling_symlink_are_not_replaced(self):
        self.destination.parent.mkdir()
        self.destination.write_bytes(b"existing")
        with self.assertRaises(FileExistsError):
            installer.install_latest(self.destination)
        self.assertEqual(self.destination.read_bytes(), b"existing")
        self.destination.unlink()
        missing = self.root / "missing"
        self.destination.symlink_to(missing)
        with self.assertRaises(FileExistsError):
            installer.install_latest(self.destination)
        self.assertEqual(self.destination.readlink(), missing)
        self.urlopen.assert_not_called()

    def test_destination_created_during_install_is_not_replaced(self):
        self.fixture(make_archive())
        real_link = os.link

        def competing_install(source, destination):
            self.destination.write_bytes(b"winner")
            real_link(source, destination)

        with patch.object(installer.os, "link", side_effect=competing_install):
            with self.assertRaises(FileExistsError):
                installer.install_latest(self.destination)
        self.assertEqual(self.destination.read_bytes(), b"winner")
        self.assertEqual(list(self.destination.parent.iterdir()), [self.destination])

    def test_discovery_checks_executable_regular_files_in_order(self):
        base = self.root / "app"
        (base / "miner").mkdir(parents=True)
        with patch.dict(os.environ, {"XDG_DATA_HOME": str(self.root / "xdg")}):
            user = installer.user_miner_path()
            self.assertEqual(user, self.root / "xdg/xmrigui/miner/xmrig")
            user.parent.mkdir(parents=True)
            # Ignore the real /opt candidate on the machine running the tests.
            with patch.object(installer, "Path", wraps=Path) as path:
                path.side_effect = lambda value: (
                    self.root / "absent"
                    if value == "/opt/xmrigui/xmrig"
                    else Path(value)
                )
                (base / "xmrig").mkdir()
                nested = base / "miner/xmrig"
                nested.write_bytes(BINARY)
                nested.chmod(0o644)
                self.assertIsNone(installer.discover_miner(base))
                user.write_bytes(BINARY)
                user.chmod(0o755)
                self.assertEqual(installer.discover_miner(base), user)
                nested.chmod(0o755)
                self.assertEqual(installer.discover_miner(base), nested)

    def test_user_destination_fallback(self):
        with patch.dict(
            os.environ, {"HOME": str(self.root), "XDG_DATA_HOME": "relative"}
        ):
            self.assertEqual(
                installer.user_miner_path(),
                self.root / ".local/share/xmrigui/miner/xmrig",
            )
