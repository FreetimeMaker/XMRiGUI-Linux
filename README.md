# XMRiGUI

XMRiGUI is a free and open-source crypto miner for Linux. It provides a modern, high-performance GUI for [XMRig](https://github.com/xmrig/xmrig).

Built with **Python 3** and **GTK 3**.

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

## Makefile Commands

If you want to build XMRiGUI from source, you'll need to have:

- python3
- gtk3
- pyinstaller
- pygobject
- gir1.2-ayatanaappindicator3-0.1
  <br>
  <br>

Build:

`sudo make install`

or if you want deb package:

`sudo make deb`

or for the rpm package:

`sudo make rpm`
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

Pull requests and bug reports are welcome on [GitHub](https://github.com/FreetimeMaker/XMRiGUI-Linux).

---

**Disclaimer**: Mining can be intensive for your hardware. Ensure proper cooling. Use at your own risk.
