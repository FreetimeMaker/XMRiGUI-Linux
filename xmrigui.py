#!/usr/bin/env python3

import codecs
import copy
import json
import os
import re
import shlex
import sys
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, Qt, QTimer, pyqtClassInfo, pyqtSlot
from PyQt6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
from PyQt6.QtGui import (
    QColor,
    QFontDatabase,
    QIcon,
    QIntValidator,
    QPixmap,
    QTextCharFormat,
    QTextCursor,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSystemTrayIcon,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from mining_tools import HashrateChart, SessionStats, redact_log, validate_settings

SERVICE = "com.freetime.xmrigui"
OBJECT_PATH = "/com/freetime/xmrigui"


@pyqtClassInfo("D-Bus Interface", SERVICE)
class DBUSService(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window

    @pyqtSlot(str)
    def startup(self, args):
        self.args_manager(args)

    def args_manager(self, args):
        args = args.split()
        if "stop" in args:
            for profile in self.window.profiles:
                self.window.widgets[profile]["mine_switch"].setChecked(False)
        elif "start" in args:
            for profile in self.window.profiles:
                self.window.widgets[profile]["mine_switch"].setChecked(True)
        if "--close" in args:
            self.window.hide()
        elif "--open" in args or not args:
            self.window.show_window()


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.widgets = {}
        self.processes = {}
        self.shutting_down = False
        self.load_data()
        self.config = self.get_config()
        self.draw()
        self.tray = self.build_tray()
        self.stats_timer = QTimer(self)
        self.stats_timer.timeout.connect(self.refresh_stats)
        self.stats_timer.start(1000)
        for profile in self.profiles:
            if self.config[profile]["mine"]:
                self.start_mining(profile, save=False)

    def load_data(self):
        base = Path(__file__).resolve().parent
        self.settings_path = Path.home() / ".config" / "xmrigui.json"
        installed_miner = Path("/opt/xmrigui/xmrig")
        self.xmrig_path = str(
            installed_miner if installed_miner.exists() else base / "xmrig"
        )
        installed_icon = Path("/usr/share/icons/hicolor/256x256/apps/xmrigui.png")
        self.icon_path = str(
            installed_icon if installed_icon.exists() else base / "xmrigui.png"
        )
        self.cuda_plugin_path = "/opt/xmrigui/libxmrig-cuda.so"
        self.profiles = ["profile-0", "profile-1", "profile-2"]
        self.cryptos = [
            "Monero",
            "Ravencoin",
            "Uplexa",
            "Chukwa",
            "Chukwa v2",
            "CCX",
            "Keva",
            "Dero",
            "Talleo",
            "Safex",
            "ArQmA",
            "NINJA",
            "Raptoreum",
            "Wownero",
            "Scala",
            "Haven Protocol",
            "MoneroV",
            "Epic Cash",
            "Graft",
            "Oxen",
            "Stellite",
        ]
        self.algos = [
            "rx/0",
            "kawpow",
            "cn/upx2",
            "argon2/chukwa",
            "argon2/chukwav2",
            "cn/ccx",
            "rx/keva",
            "astrobwt",
            "cn-pico/tlo",
            "rx/sfx",
            "rx/arq",
            "argon2/ninja",
            "gr",
            "rx/wow",
            "panthera",
            "cn-heavy/xhv",
            "rx/v",
            "rx/epic",
            "rx/graft",
            "rx/loki",
            "rx/xtl",
        ]
        pools = [
            "xmr-eu.kryptex.network:7029",
            "pool.supportxmr.com:3333",
            "xmr-eu1.nanopool.org:10300",
        ]
        self.defaults = {
            profile: {
                "mine": False,
                "name": f"Profile {self.profiles.index(profile) + 1}",
                "auto_restart": False,
                "pool": pool,
                "user": "49szz88CqMWGgyDxp7VqvBS62pGLQcV4YPSBHcLwtxAXLz1Wngf8vW6is4w13Au7C2RovrTiJQaGDV5VBhFnyMBsM44Pn2P",
                "password": "DONATE",
                "donate": "0",
                "threads": "8",
                "cuda": False,
                "opencl": False,
                "cpu": True,
                "coin": 0,
                "args": "",
                "default_args": False,
            }
            for profile, pool in zip(self.profiles, pools)
        }

    def get_config(self):
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.settings_path.exists():
            config = self.defaults
            self.settings_path.write_text(json.dumps(config), encoding="utf-8")
            return config
        # Do not overwrite an existing configuration if it cannot be read.
        config = json.loads(self.settings_path.read_text(encoding="utf-8"))
        for profile in self.profiles:
            config[profile] = {**self.defaults[profile], **config.get(profile, {})}
            coin = config[profile]["coin"]
            if not isinstance(coin, int) or not 0 <= coin < len(self.algos):
                config[profile]["coin"] = 0
        return config

    def draw(self):
        self.setWindowTitle("XMRiGUI v2.0.0")
        self.setWindowIcon(QIcon(self.icon_path))
        self.resize(800, 720)
        tabs = QTabWidget()
        self.setCentralWidget(tabs)
        self.tabs = tabs
        for number, profile in enumerate(self.profiles, 1):
            config = self.config[profile]
            widgets = self.widgets[profile] = {}
            widgets["stats"] = SessionStats()
            widgets["retries"] = 0
            widgets["restart_timer"] = QTimer(self)
            widgets["restart_timer"].setSingleShot(True)
            widgets["restart_timer"].timeout.connect(
                lambda p=profile: self.start_mining(p, save=False, retry=True)
            )
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(20, 20, 20, 20)
            layout.setSpacing(15)
            header = QHBoxLayout()
            image = QLabel()
            image.setPixmap(
                QPixmap(self.icon_path).scaled(
                    96,
                    96,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            header.addWidget(image)
            name = QLabel(
                "<h2>XMRiGUI</h2>made by Freetime Maker<br>"
                '<a href="https://github.com/FreetimeMaker/XMRiGUI-Linux">Source code</a>'
            )
            name.setOpenExternalLinks(True)
            header.addWidget(name)
            header.addStretch()
            mining = QVBoxLayout()
            widgets["mine_switch"] = QCheckBox("Mine")
            widgets["mine_switch"].setChecked(config["mine"])
            widgets["status_label"] = QLabel("Status: Stopped.")
            widgets["info_label"] = QLabel("<b>Speed:</b> 0 H/s | <b>Shares:</b> 0/0")
            for key in ("mine_switch", "status_label", "info_label"):
                mining.addWidget(widgets[key])
            header.addLayout(mining)
            layout.addLayout(header)

            profile_buttons = QHBoxLayout()
            for title, callback in (
                ("Rename profile", self.rename_profile),
                ("Duplicate profile…", self.duplicate_profile),
            ):
                button = QPushButton(title)
                button.clicked.connect(
                    lambda checked=False, p=profile, fn=callback: fn(p)
                )
                profile_buttons.addWidget(button)
            layout.addLayout(profile_buttons)
            form = QFormLayout()
            for key, label, setting in (
                ("pool_entry", "Pool:", "pool"),
                ("user_entry", "User:", "user"),
                ("pass_entry", "Password:", "password"),
                ("donate_entry", "Donate:", "donate"),
                ("threads_entry", "Threads:", "threads"),
            ):
                widgets[key] = QLineEdit(str(config[setting]))
                if setting in ("threads", "donate"):
                    widgets[key].setValidator(
                        QIntValidator(
                            0, 100 if setting == "donate" else 2147483647, self
                        )
                    )
                form.addRow(label, widgets[key])
                error = widgets[setting + "_error"] = QLabel()
                error.setStyleSheet("color: #d64545")
                error.setWordWrap(True)
                form.addRow(error)
            save_button = QPushButton("Save")
            save_button.clicked.connect(lambda checked=False: self.save())
            form.addRow(save_button)
            layout.addLayout(form)

            advanced = QGroupBox("Advanced options")
            advanced.setCheckable(True)
            advanced.setChecked(False)
            advanced_content = QWidget()
            advanced_form = QFormLayout(advanced_content)
            for key, label in (
                ("cuda", "NVidia GPU"),
                ("opencl", "AMD GPU"),
                ("cpu", "CPU"),
                ("default_args", "Disable default args"),
            ):
                checkbox = QCheckBox(label)
                checkbox.setChecked(config[key])
                widgets[f"{key}_switch"] = checkbox
                advanced_form.addRow(checkbox)
            widgets["crypto_chooser"] = QComboBox()
            widgets["crypto_chooser"].addItems(self.cryptos)
            widgets["crypto_chooser"].setCurrentIndex(config["coin"])
            advanced_form.addRow("Coin:", widgets["crypto_chooser"])
            widgets["args_entry"] = QLineEdit(config["args"])
            advanced_form.addRow("Additional args:", widgets["args_entry"])
            widgets["args_error"] = QLabel()
            advanced_form.addRow(widgets["args_error"])
            widgets["auto_restart_switch"] = QCheckBox(
                "Restart after unexpected exit (maximum 5 attempts)"
            )
            widgets["auto_restart_switch"].setChecked(config["auto_restart"])
            advanced_form.addRow(widgets["auto_restart_switch"])
            advanced_save = QPushButton("Save")
            advanced_save.clicked.connect(lambda checked=False: self.save())
            advanced_form.addRow(advanced_save)
            QVBoxLayout(advanced).addWidget(advanced_content)
            advanced_content.hide()
            advanced.toggled.connect(advanced_content.setVisible)
            layout.addWidget(advanced)

            widgets["chart"] = HashrateChart()
            layout.addWidget(widgets["chart"])
            widgets["session_label"] = QLabel()
            layout.addWidget(widgets["session_label"])
            diagnosis = QGroupBox("Diagnostics")
            diagnostic_layout = QVBoxLayout(diagnosis)
            widgets["diagnostics"] = QLabel(
                f"Binary: {self.xmrig_path}\nVersion / Huge Pages / permissions: not reported yet"
            )
            widgets["diagnostics"].setWordWrap(True)
            diagnostic_layout.addWidget(widgets["diagnostics"])
            export = QPushButton("Export redacted log…")
            export.clicked.connect(lambda checked=False, p=profile: self.export_log(p))
            diagnostic_layout.addWidget(export)
            layout.addWidget(diagnosis)

            output = QGroupBox("Miner Output (Live)")
            output.setCheckable(True)
            output.setChecked(False)
            log = widgets["log_view"] = QTextEdit()
            log.setReadOnly(True)
            log.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
            log.document().setMaximumBlockCount(500)
            log.setMinimumHeight(150)
            QVBoxLayout(output).addWidget(log)
            log.hide()
            output.toggled.connect(log.setVisible)
            layout.addWidget(output)
            layout.addStretch()
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            tabs.addTab(scroll, str(config["name"]))

        # Connect only after every profile's controls are ready for save().
        for profile in self.profiles:
            widgets = self.widgets[profile]
            widgets["mine_switch"].toggled.connect(
                lambda checked, p=profile: self.set_mining(p, checked)
            )
            for key in ("cuda", "opencl", "cpu", "default_args", "auto_restart"):
                widgets[f"{key}_switch"].toggled.connect(lambda checked: self.save())
            widgets["crypto_chooser"].currentIndexChanged.connect(
                lambda index: self.save()
            )

    def save(self, restart=True):
        for profile in self.profiles:
            widgets = self.widgets[profile]
            config = self.config[profile]
            for setting, key in (
                ("pool", "pool_entry"),
                ("user", "user_entry"),
                ("password", "pass_entry"),
                ("donate", "donate_entry"),
                ("threads", "threads_entry"),
                ("args", "args_entry"),
            ):
                config[setting] = widgets[key].text()
            for key in ("cuda", "opencl", "cpu", "default_args", "auto_restart"):
                config[key] = widgets[f"{key}_switch"].isChecked()
            config["coin"] = widgets["crypto_chooser"].currentIndex()
        self.settings_path.write_text(json.dumps(self.config), encoding="utf-8")
        if restart:
            for profile in self.profiles:
                if self.config[profile]["mine"]:
                    self.stop_mining(profile, save=False)
                    self.start_mining(profile, save=False)

    def set_mining(self, profile, enabled):
        if enabled:
            self.start_mining(profile)
        else:
            self.stop_mining(profile)

    def sync_mine_switch(self, profile, enabled):
        checkbox = self.widgets[profile]["mine_switch"]
        previous = checkbox.blockSignals(True)
        checkbox.setChecked(enabled)
        checkbox.blockSignals(previous)

    def mining_arguments(self, profile):
        config = self.config[profile]
        args = ["--no-color"]
        if not config["default_args"]:
            args.extend(
                [
                    f"--algo={self.algos[config['coin']]}",
                    f"--url={config['pool']}",
                    f"--user={config['user']}",
                    f"--pass={config['password']}",
                    f"--donate-level={config['donate']}",
                ]
            )
            if config["threads"] and config["threads"] != "0":
                args.extend(
                    [
                        f"--threads={config['threads']}",
                        f"--randomx-init={config['threads']}",
                    ]
                )
            if config["cuda"]:
                args.extend(["--cuda", f"--cuda-loader={self.cuda_plugin_path}"])
            if config["opencl"]:
                args.append("--opencl")
            if not config["cpu"]:
                args.append("--no-cpu")
        args.extend(shlex.split(config["args"]))
        return args

    def start_mining(self, profile, save=True, retry=False):
        if profile in self.processes:
            return
        if save:
            self.config[profile]["mine"] = True
            self.save(restart=False)
        widgets = self.widgets[profile]
        widgets["restart_timer"].stop()
        errors = validate_settings(self.config[profile])
        for key in ("pool", "user", "threads", "donate", "args"):
            widgets[key + "_error"].setText(errors.get(key, ""))
            widgets[
                {
                    "pool": "pool_entry",
                    "user": "user_entry",
                    "threads": "threads_entry",
                    "donate": "donate_entry",
                    "args": "args_entry",
                }[key]
            ].setToolTip(errors.get(key, ""))
        if errors:
            self.mining_failed(
                profile, "Invalid settings: " + "; ".join(errors.values())
            )
            return
        if not retry:
            widgets["retries"] = 0
            widgets["stats"].start()
            widgets["chart"].clear()
            widgets["last_speed"] = "0.0"
            widgets["last_shares"] = "0/0"
        self.sync_mine_switch(profile, True)
        try:
            args = self.mining_arguments(profile)
        except ValueError as error:
            self.mining_failed(profile, str(error))
            return
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.processes[profile] = process
        widgets = self.widgets[profile]
        widgets["pending_output"] = ""
        widgets["decoder"] = codecs.getincrementaldecoder("utf-8")(errors="replace")
        process.readyReadStandardOutput.connect(
            lambda: self.read_output(profile, process)
        )
        process.errorOccurred.connect(
            lambda error: self.process_error(profile, process, error)
        )
        process.finished.connect(
            lambda code, status: self.process_finished(profile, process, code)
        )
        widgets["status_label"].setText("Status: Starting…")
        process.start(self.xmrig_path, args)

    def stop_mining(self, profile, save=True):
        self.widgets[profile]["restart_timer"].stop()
        self.widgets[profile]["stats"].stop()
        process = self.processes.pop(profile, None)
        if process is not None:
            # Stop only this profile's child, never unrelated XMRig processes.
            process.terminate()
            if not process.waitForFinished(1500):
                process.kill()
                process.waitForFinished(1500)
            self.read_output(profile, process, final=True)
            process.deleteLater()
        self.widgets[profile]["status_label"].setText("Status: Stopped.")
        if save:
            self.config[profile]["mine"] = False
            self.sync_mine_switch(profile, False)
            self.save(restart=False)

    def mining_failed(self, profile, message):
        self.widgets[profile]["stats"].stop()
        self.config[profile]["mine"] = False
        self.sync_mine_switch(profile, False)
        self.widgets[profile]["status_label"].setText(f"Error: {message}")
        self.save(restart=False)

    def process_error(self, profile, process, error):
        if self.processes.get(profile) is not process:
            return
        if error == QProcess.ProcessError.FailedToStart:
            self.processes.pop(profile)
            self.mining_failed(profile, process.errorString())
            process.deleteLater()

    def process_finished(self, profile, process, code):
        if self.processes.get(profile) is not process:
            return
        self.read_output(profile, process, final=True)
        self.processes.pop(profile)
        widgets = self.widgets[profile]
        if (
            not self.shutting_down
            and self.config[profile]["mine"]
            and self.config[profile]["auto_restart"]
            and widgets["retries"] < 5
        ):
            delay = min(60, 2 ** (widgets["retries"] + 1))
            widgets["retries"] += 1
            widgets["last_speed"] = "0.0"
            widgets["chart"].add_sample(0)
            widgets["status_label"].setText(
                f"Status: Connection lost / miner exited ({code}). Restart {widgets['retries']}/5 in {delay}s"
            )
            widgets["restart_timer"].start(delay * 1000)
        else:
            self.mining_failed(
                profile,
                f"Miner exited (code {code}); automatic restart disabled or limit reached.",
            )
        process.deleteLater()

    def read_output(self, profile, process, final=False):
        widgets = self.widgets[profile]
        text = widgets["decoder"].decode(
            bytes(process.readAllStandardOutput()), final=final
        )
        text = widgets["pending_output"] + text
        lines = text.split("\n")
        widgets["pending_output"] = lines.pop()
        if final and widgets["pending_output"]:
            lines.append(widgets["pending_output"])
            widgets["pending_output"] = ""
        for line in lines:
            self.update_log(profile, line.rstrip("\r"))

    def update_log(self, profile, line):
        widgets = self.widgets[profile]
        lower_line = line.lower()
        color = None
        if "accepted" in lower_line:
            color = "#2ecc71"
        elif any(word in lower_line for word in ("error", "rejected", "failed")):
            color = "#e74c3c"
        elif "net" in lower_line or "pool" in lower_line:
            color = "#3498db"
        elif "speed" in lower_line:
            color = "#f1c40f"
        log = widgets["log_view"]
        cursor = log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        text_format = QTextCharFormat()
        if color:
            text_format.setForeground(QColor(color))
        cursor.insertText(line + "\n", text_format)
        log.setTextCursor(cursor)
        log.ensureCursorVisible()
        speed = re.search(r"speed 10s/60s/15m\s+([\d.]+)", line)
        if speed:
            unit = re.search(r"\b([kMGT]?)H/s", line)
            value = float(speed.group(1)) * {
                "": 1,
                "k": 1e3,
                "M": 1e6,
                "G": 1e9,
                "T": 1e12,
            }.get(unit.group(1) if unit else "", 1)
            widgets["last_speed"] = f"{value:g}"
            widgets["stats"].add_speed(value)
            widgets["chart"].add_sample(value)
        shares = re.search(r"(?:accepted|rejected)\s+\((\d+)/(\d+)\)", line)
        if shares:
            widgets["last_shares"] = f"{shares.group(1)}/{shares.group(2)}"
            widgets["stats"].update_shares(int(shares.group(1)), int(shares.group(2)))
        widgets["info_label"].setText(
            f"<b>Speed:</b> {widgets.get('last_speed', '0.0')} H/s | "
            f"<b>Shares:</b> {widgets.get('last_shares', '0/0')}"
        )
        if any(
            word in lower_line
            for word in (
                "xmrig",
                "huge pages",
                "hugepages",
                "permission",
                "msr",
                "access denied",
            )
        ):
            previous = widgets["diagnostics"].text().splitlines()[-9:]
            widgets["diagnostics"].setText("\n".join(previous + [line]))
        if any(
            word in lower_line
            for word in (
                "connection refused",
                "connection reset",
                "timeout",
                "no active pools",
                "dns error",
                "connect error",
            )
        ):
            widgets["status_label"].setText(
                "Status: Connection lost; XMRig is reconnecting…"
            )
        elif "connected to" in lower_line:
            pool = re.search(r"to\s+([^\s]+)", line)
            widgets["status_label"].setText(
                f"Status: Connected with {pool.group(1) if pool else 'Pool'}"
            )
        elif "new job" in lower_line:
            widgets["status_label"].setText("Status: Neuer Job erhalten")
        elif "ready" in lower_line:
            widgets["status_label"].setText("Status: Bereit")
        elif "accepted" in lower_line:
            widgets["status_label"].setText("Status: Mining (Share akzeptiert!)")

    def refresh_stats(self):
        for widgets in self.widgets.values():
            stats = widgets["stats"].snapshot()
            seconds = int(stats["runtime"])
            widgets["session_label"].setText(
                f"Runtime: {seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02} | "
                f"Average (samples): {stats['average']:.1f} H/s | "
                f"Rejected: {stats['rejection_ratio']:.1%}"
            )

    def rename_profile(self, profile):
        name, ok = QInputDialog.getText(
            self, "Rename profile", "Name:", text=self.config[profile]["name"]
        )
        if ok and name.strip():
            self.config[profile]["name"] = name.strip()[:80]
            self.tabs.setTabText(
                self.profiles.index(profile), self.config[profile]["name"]
            )
            self.save(restart=False)
            self.refresh_tray_names()

    def duplicate_profile(self, profile):
        targets = [p for p in self.profiles if p != profile]
        labels = [f"{self.config[p]['name']} ({p})" for p in targets]
        choice, ok = QInputDialog.getItem(
            self, "Duplicate profile", "Replace target profile:", labels, 0, False
        )
        if not ok:
            return
        target = targets[labels.index(choice)]
        if (
            QMessageBox.question(
                self,
                "Replace profile",
                "Overwrite this profile's settings and stop its miner?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.save(restart=False)
        self.stop_mining(target, save=False)
        config = copy.deepcopy(self.config[profile])
        config.update(mine=False, name=config["name"] + " (copy)")
        self.config[target] = config
        w = self.widgets[target]
        for key in ("pool", "user", "password", "donate", "threads", "args"):
            w[{"password": "pass_entry"}.get(key, key + "_entry")].setText(
                str(config[key])
            )
        controls = [
            (w[key + "_switch"], config[key])
            for key in ("cuda", "opencl", "cpu", "default_args", "auto_restart")
        ]
        for control, value in controls:
            blocked = control.blockSignals(True)
            control.setChecked(value)
            control.blockSignals(blocked)
        chooser = w["crypto_chooser"]
        blocked = chooser.blockSignals(True)
        chooser.setCurrentIndex(config["coin"])
        chooser.blockSignals(blocked)
        self.sync_mine_switch(target, False)
        self.tabs.setTabText(self.profiles.index(target), config["name"])
        self.save(restart=False)
        self.refresh_tray_names()

    def refresh_tray_names(self):
        if self.tray is not None:
            for profile, action in zip(
                self.profiles, self.tray.contextMenu().actions()
            ):
                action.setText("Toggle " + self.config[profile]["name"])

    def export_log(self, profile):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export redacted log", "xmrigui-log.txt", "Text files (*.txt)"
        )
        if not filename:
            return
        w = self.widgets[profile]
        draft = dict(
            self.config[profile],
            user=w["user_entry"].text(),
            password=w["pass_entry"].text(),
            pool=w["pool_entry"].text(),
            args=w["args_entry"].text(),
        )
        text = w["diagnostics"].text() + "\n\n" + w["log_view"].toPlainText()
        try:
            Path(filename).write_text(
                redact_log(text, [*self.config.values(), draft]), encoding="utf-8"
            )
        except OSError as error:
            QMessageBox.warning(self, "Export failed", str(error))

    def build_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return None
        tray = QSystemTrayIcon(self.windowIcon(), self)
        tray.setToolTip("XMRiGUI")
        menu = QMenu(self)
        for number, profile in enumerate(self.profiles, 1):
            menu.addAction("Toggle " + self.config[profile]["name"]).triggered.connect(
                lambda checked=False, p=profile: self.widgets[p]["mine_switch"].toggle()
            )
        menu.addSeparator()
        menu.addAction("Show").triggered.connect(self.show_window)
        menu.addAction("Quit").triggered.connect(QApplication.instance().quit)
        tray.setContextMenu(menu)
        tray.activated.connect(self.tray_activated)
        tray.show()
        return tray

    def tray_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_window()

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        if self.tray is not None and not self.shutting_down:
            self.hide()
            event.ignore()
        else:
            event.accept()
            QApplication.instance().quit()

    def shutdown(self):
        self.shutting_down = True
        self.stats_timer.stop()
        for profile in self.profiles:
            self.stop_mining(profile, save=False)
        if self.tray is not None:
            self.tray.hide()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("XMRiGUI")
    app.setDesktopFileName("xmrigui")
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        print(
            "Cannot connect to the session D-Bus: " + bus.lastError().message(),
            file=sys.stderr,
        )
        return 1
    # Acquire the name before loading settings or starting any miner.
    if not bus.registerService(SERVICE):
        interface = QDBusInterface(SERVICE, OBJECT_PATH, SERVICE, bus)
        reply = interface.call("startup", " ".join(sys.argv[1:]))
        if reply.type() == QDBusMessage.MessageType.ErrorMessage:
            print(reply.errorMessage(), file=sys.stderr)
            return 1
        print("Another instance was running and notified.")
        return 0
    try:
        window = Window()
    except (OSError, ValueError, TypeError) as error:
        QMessageBox.critical(None, "XMRiGUI", f"Cannot load settings: {error}")
        return 1
    service = DBUSService(window)
    if not bus.registerObject(
        OBJECT_PATH, service, QDBusConnection.RegisterOption.ExportAllSlots
    ):
        window.shutdown()
        print(bus.lastError().message(), file=sys.stderr)
        return 1
    app.setQuitOnLastWindowClosed(window.tray is None)
    app.aboutToQuit.connect(window.shutdown)
    window.show()
    service.args_manager(" ".join(sys.argv[1:]))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
