import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtDBus import QDBusConnection
from PyQt6.QtWidgets import QApplication

import xmrigui


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        original_load = xmrigui.Window.load_data

        def load_data(window):
            original_load(window)
            window.settings_path = Path(self.temp.name) / "config" / "xmrigui.json"

        with (
            patch.object(xmrigui.Window, "load_data", load_data),
            patch.object(
                xmrigui.QSystemTrayIcon, "isSystemTrayAvailable", return_value=False
            ),
        ):
            self.window = xmrigui.Window()

    def tearDown(self):
        self.window.shutdown()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def wait_until(self, predicate):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(0.01)
        self.fail("Timed out waiting for Qt event")

    def fake_miner(self, profile):
        script = Path(self.temp.name) / "fake miner.py"
        script.write_text(
            "import time\n"
            'print("speed 10s/60s/15m 42.5 40 39 H/s", flush=True)\n'
            'print("accepted (3/0)", flush=True)\n'
            "time.sleep(30)\n",
            encoding="utf-8",
        )
        self.window.xmrig_path = sys.executable
        widgets = self.window.widgets[profile]
        widgets["default_args_switch"].setChecked(True)
        # Python consumes --no-color as an interpreter option, so replace the
        # argument builder only for this fake miner, not production execution.
        self.window.mining_arguments = lambda p: [str(script)]
        widgets["args_entry"].setText(shlex.quote(str(script)))

    def test_profiles_and_saved_config(self):
        self.assertEqual(self.window.centralWidget().count(), 3)
        self.window.widgets["profile-1"]["pool_entry"].setText("example.org:3333")
        self.window.save(restart=False)
        config = json.loads(self.window.settings_path.read_text())
        self.assertEqual(config["profile-1"]["pool"], "example.org:3333")
        self.assertEqual(self.window.get_config(), config)

    def test_show_does_not_recreate_controls(self):
        control = self.window.widgets["profile-0"]["pool_entry"]
        control.setText("unsaved edit")
        self.window.hide()
        self.window.show_window()
        self.assertIs(control, self.window.widgets["profile-0"]["pool_entry"])
        self.assertEqual(control.text(), "unsaved edit")

    def test_arguments_are_not_shell_commands(self):
        widgets = self.window.widgets["profile-0"]
        widgets["user_entry"].setText("wallet; touch /tmp/not-executed")
        widgets["args_entry"].setText('--rig-id "worker one"')
        self.window.save(restart=False)
        args = self.window.mining_arguments("profile-0")
        self.assertIn("--user=wallet; touch /tmp/not-executed", args)
        self.assertEqual(args[-2:], ["--rig-id", "worker one"])
        widgets["threads_entry"].setText("0")
        self.window.save(restart=False)
        self.assertFalse(
            any(
                arg.startswith("--threads=")
                for arg in self.window.mining_arguments("profile-0")
            )
        )

    def test_log_stats_and_limit(self):
        self.window.update_log("profile-0", "speed 10s/60s/15m 123.4 100 99 H/s")
        self.window.update_log("profile-0", "accepted (12/1)")
        widgets = self.window.widgets["profile-0"]
        self.assertIn("123.4 H/s", widgets["info_label"].text())
        self.assertIn("12/1", widgets["info_label"].text())
        for index in range(600):
            self.window.update_log("profile-0", f"line {index}")
        self.assertLessEqual(widgets["log_view"].document().blockCount(), 500)

    def test_independent_processes_and_output(self):
        self.fake_miner("profile-0")
        for profile in ("profile-0", "profile-1"):
            self.window.widgets[profile]["mine_switch"].setChecked(True)
        self.wait_until(
            lambda: self.window.widgets["profile-0"].get("last_shares") == "3/0"
        )
        other = self.window.processes["profile-1"]
        self.window.widgets["profile-0"]["mine_switch"].setChecked(False)
        self.assertNotIn("profile-0", self.window.processes)
        self.assertIs(self.window.processes["profile-1"], other)
        self.assertTrue(self.window.config["profile-1"]["mine"])

    def test_failed_start_resets_switch(self):
        self.window.xmrig_path = str(Path(self.temp.name) / "missing-miner")
        self.window.widgets["profile-0"]["mine_switch"].setChecked(True)
        self.wait_until(lambda: not self.window.config["profile-0"]["mine"])
        self.assertFalse(self.window.widgets["profile-0"]["mine_switch"].isChecked())
        self.assertIn("Error:", self.window.widgets["profile-0"]["status_label"].text())
        self.assertNotIn("profile-0", self.window.processes)

    def test_normal_exit_flushes_partial_output(self):
        self.window.xmrig_path = sys.executable
        self.window.mining_arguments = lambda profile: [
            "-c",
            'print("last line", end="")',
        ]
        self.window.widgets["profile-0"]["mine_switch"].setChecked(True)
        self.wait_until(lambda: not self.window.config["profile-0"]["mine"])
        self.assertIn(
            "last line", self.window.widgets["profile-0"]["log_view"].toPlainText()
        )
        self.assertNotIn("profile-0", self.window.processes)

    def test_validation_blocks_start_and_marks_field(self):
        w = self.window.widgets["profile-0"]
        w["pool_entry"].setText("not a pool")
        w["mine_switch"].setChecked(True)
        self.assertNotIn("profile-0", self.window.processes)
        self.assertTrue(w["pool_error"].text())
        self.assertFalse(w["mine_switch"].isChecked())

    def test_restart_backoff_and_manual_stop_cancels(self):
        profile = "profile-0"
        self.window.xmrig_path = sys.executable
        self.window.mining_arguments = lambda p: ["-c", "print('connection refused')"]
        w = self.window.widgets[profile]
        w["auto_restart_switch"].setChecked(True)
        w["mine_switch"].setChecked(True)
        self.wait_until(lambda: w["restart_timer"].isActive())
        self.assertEqual(w["retries"], 1)
        self.assertTrue(self.window.config[profile]["mine"])
        w["mine_switch"].setChecked(False)
        self.assertFalse(w["restart_timer"].isActive())
        self.assertFalse(self.window.config[profile]["mine"])

    def test_restart_limit(self):
        profile = "profile-0"
        self.window.xmrig_path = sys.executable
        self.window.mining_arguments = lambda p: ["-c", "pass"]
        w = self.window.widgets[profile]
        w["auto_restart_switch"].setChecked(True)
        w["mine_switch"].setChecked(True)
        self.wait_until(lambda: w["restart_timer"].isActive())
        w["restart_timer"].stop()
        w["retries"] = 5
        self.window.start_mining(profile, save=False, retry=True)
        self.wait_until(lambda: not self.window.config[profile]["mine"])
        self.assertFalse(w["restart_timer"].isActive())

    def test_profile_rename_and_duplicate(self):
        with patch.object(
            xmrigui.QInputDialog, "getText", return_value=("Quiet CPU", True)
        ):
            self.window.rename_profile("profile-0")
        self.assertEqual(self.window.tabs.tabText(0), "Quiet CPU")
        target = self.window.config["profile-1"]["name"] + " (profile-1)"
        with (
            patch.object(xmrigui.QInputDialog, "getItem", return_value=(target, True)),
            patch.object(
                xmrigui.QMessageBox,
                "question",
                return_value=xmrigui.QMessageBox.StandardButton.Yes,
            ),
        ):
            self.window.duplicate_profile("profile-0")
        self.assertEqual(self.window.config["profile-1"]["name"], "Quiet CPU (copy)")
        self.assertFalse(self.window.config["profile-1"]["mine"])
        self.assertIsNot(
            self.window.config["profile-0"], self.window.config["profile-1"]
        )

    def test_invalid_config_is_not_overwritten(self):
        self.window.settings_path.write_text("{broken")
        with self.assertRaises(ValueError):
            self.window.get_config()
        self.assertEqual(self.window.settings_path.read_text(), "{broken")

    def test_dbus_commands_use_window_profiles(self):
        service = xmrigui.DBUSService(self.window)
        with patch.object(self.window, "start_mining") as start:
            service.args_manager("start --close")
            self.assertEqual(start.call_count, 3)
        with patch.object(self.window, "stop_mining") as stop:
            service.args_manager("stop --open")
            self.assertEqual(stop.call_count, 3)
        self.assertTrue(self.window.isVisible())


class SingleInstanceTests(unittest.TestCase):
    def test_forwarding_before_settings_are_loaded(self):
        if not QDBusConnection.sessionBus().isConnected():
            self.skipTest("Run under dbus-run-session for D-Bus integration")
        with tempfile.TemporaryDirectory() as temp:
            ready = Path(temp) / "ready"
            received = Path(temp) / "received"
            # The first process exports the production D-Bus class without
            # opening real settings or launching a miner.
            server = """
import sys
from pathlib import Path
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtDBus import QDBusConnection
import xmrigui
app = QApplication([])
window = QWidget()
service = xmrigui.DBUSService(window)
service.args_manager = lambda args: Path(sys.argv[2]).write_text(args)
bus = QDBusConnection.sessionBus()
assert bus.registerService(xmrigui.SERVICE)
assert bus.registerObject(xmrigui.OBJECT_PATH, service, QDBusConnection.RegisterOption.ExportAllSlots)
Path(sys.argv[1]).touch()
QTimer.singleShot(15000, app.quit)
app.exec()
"""
            process = subprocess.Popen(
                [sys.executable, "-c", server, str(ready), str(received)]
            )
            try:
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(ready.exists(), "D-Bus server failed to register")
                client = """
import sys
from unittest.mock import patch
import xmrigui
sys.argv = ['xmrigui', 'stop', '--open']
with patch.object(xmrigui.Window, 'load_data', side_effect=AssertionError('Settings touched')):
    sys.exit(xmrigui.main())
"""
                result = subprocess.run(
                    [sys.executable, "-c", client],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(received.read_text(), "stop --open")
            finally:
                process.terminate()
                process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
