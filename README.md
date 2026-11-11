# XMRiGUI

XMRiGUI is a free and open-source crypto miner for Linux. It provides a modern, high-performance GUI for [XMRig](https://github.com/xmrig/xmrig).

Built with **Python 3** and **PyQt6**. D-Bus integration uses **QtDBus**, which is included in PyQt6 (no separate `dbus-python` package is needed).

![Preview of XMRiGUI](preview.png)

## This Repo is sponsored by

[![Sponsor](https://readme.cash/i/9s3hhz665u.svg)](https://readme.cash/c/9s3hhz665u)

## Features

### Supported Miners

- **XMRig**: For Monero, Ravencoin, and most CPU-based coins.

### Key Capabilities

- **Multi-Profile Support**: Manage up to 3 different mining configurations simultaneously.
- **Intelligent Auto-Switching**: Automatically selects the best miner binary based on the selected coin.
- **Real-time Stats**: Live tracking of Hashrate (H/s) and Shares (Accepted/Rejected).
- **System Tray Integration**: Run the miner in the background with quick-access controls.
- **Pre-start validation**: Field-level errors for pool addresses, empty users, thread/donation ranges and malformed argument quoting. Threads `0` means automatic selection; donation accepts `0–100` (the miner may impose its own minimum).
- **Session statistics**: A bounded, time-based hashrate chart, runtime, sample-average hashrate and rejected-share percentage. A manual start begins a fresh session; automatic retries keep its history. Values come from XMRig output, not a profitability estimate.
- **Controlled restart**: Optional per-profile automatic restart after unexpected process exit, with delays of 2, 4, 8, 16 and 32 seconds. After five retries it stops. Manual stop cancels pending retries; connection errors while XMRig is alive are left to its own reconnect logic. Disabled by default.
- **Diagnostics and log export**: Displays the binary path and version, Huge Pages, MSR and permission messages when reported by XMRig. Export masks configured credentials, pools, additional arguments and common credential patterns. Redaction is best-effort: review exported logs before sharing. Only the latest 500 log blocks are retained.
- **Named profiles**: Rename profiles and copy settings into another of the three slots, with confirmation before overwriting. The destination miner is stopped and never starts automatically after copying.
- **Cross-Platform**: Native look and feel on both Linux.

## Installation

### Linux

#### Debian / Ubuntu (APT)

1. Download the `.deb` file or use the APT Repository:

```bash
sudo nano /etc/apt/sources.list.d/Freetime-Repo.list
```

then add:

```text
deb [trusted=yes arch=amd64] https://apt.fury.io/freetimemaker/ /
```

then run:

```bash
sudo apt update
sudo apt install xmrigui
```

#### Fedora / Red Hat (RPM)

1. Download the `.rpm` file or use the YUM Repository:

```bash
sudo nano /etc/yum.repos.d/Freetime-Repo.repo
```

then add:

```text
[freetimemaker]
name=Freetime Repo
baseurl=https://yum.fury.io/freetimemaker/
enabled=1
gpgcheck=0
```

then run:

```bash
sudo dnf install xmrigui
```

## Running from Source

Run these commands from the repository root using Python 3.9 or newer:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python xmrigui.py
```

On Debian / Ubuntu, install `python3-venv` to create the virtual environment. Alternatively, use the system packages without a virtual environment:

```bash
sudo apt install python3 python3-pyqt6 python3-requests
python3 xmrigui.py
```

`PyQt6.QtDBus` is included in PyQt6 / `python3-pyqt6`; GTK, PyGObject, AppIndicator bindings and `dbus-python` are not required by the migrated app.

**Migration status:** These dependencies and instructions target the PyQt6 app. If your checkout's `xmrigui.py` still imports `gi` or `dbus`, its app-code migration must be completed before it can run with these dependencies.

Mining requires an executable XMRig binary at `/opt/xmrigui/xmrig`; `sudo make install` installs the bundled `xmrig` there.

## Makefile Commands

The Makefile installs the Python script and bundled miner directly; PyInstaller is not required.

Before `make install`, `make deb` or `make rpm`, the required dependencies are installed automatically using APT (Debian / Ubuntu) or DNF (Fedora / Red Hat). This includes Python, PyQt6, libuv and the packaging tool needed by the selected build target (`dpkg-deb` or `rpmbuild`). Dependency installation requires network access and uses `sudo` unless already running as root.

To skip dependency installation in an already prepared environment, use `make deb SKIP_DEPS=1` or `make rpm SKIP_DEPS=1`. Other distributions must install the dependencies manually and use `SKIP_DEPS=1`.

Install:

`sudo make install`

or if you want a deb package:

`make deb`

The Debian package declares `python3-pyqt6` as a runtime dependency, including QtDBus.

Build an RPM package:

`make rpm`
<br>
<br>

## Command Line Options

- `start`: Start mining all active profiles immediately.
- `stop`: Stop all active mining processes.

## Contribute

### Support the Project

If you find this tool useful, consider supporting development:

- **Monero (XMR)**: `49szz88CqMWGgyDxp7VqvBS62pGLQcV4YPSBHcLwtxAXLz1Wngf8vW6is4w13Au7C2RovrTiJQaGDV5VBhFnyMBsM44Pn2P`

### Development

Run the headless GUI and D-Bus tests with the development environment activated:

```bash
dbus-run-session -- python -m unittest discover -s tests -v
```

The tests use temporary configurations and fake miners; no real mining is started.

Pull requests and bug reports are welcome on [GitHub](https://github.com/FreetimeMaker/XMRiGUI-Linux).

---

**Disclaimer**: Mining can be intensive for your hardware. Ensure proper cooling. Use at your own risk.
