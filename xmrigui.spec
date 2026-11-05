Name:           xmrigui
Version:        1.8.2
Release:        1%{?dist}
Summary:        XMRiGUI Application
License:        GPLv3
BuildArch:      x86_64

Source0:        xmrigui.py
Source1:        xmrig
Source2:        xmrigui.png
Source3:        xmrigui.desktop

Requires:       python3 python3-pyqt6

%description
GUI wrapper for XMRig.

%prep

%build

%install
mkdir -p %{buildroot}/opt/xmrigui
mkdir -p %{buildroot}/usr/local/bin
mkdir -p %{buildroot}/usr/share/icons/hicolor/256x256/apps
mkdir -p %{buildroot}/usr/share/applications

install -m 755 %{_sourcedir}/xmrigui.py %{buildroot}/usr/local/bin/xmrigui
install -m 755 %{_sourcedir}/xmrig %{buildroot}/opt/xmrigui/xmrig
install -m 644 %{_sourcedir}/xmrigui.png %{buildroot}/opt/xmrigui/xmrigui.png
install -m 644 %{_sourcedir}/xmrigui.png %{buildroot}/usr/share/icons/hicolor/256x256/apps/xmrigui.png
install -m 644 %{_sourcedir}/xmrigui.desktop %{buildroot}/usr/share/applications/xmrigui.desktop

%files
/usr/local/bin/xmrigui
/opt/xmrigui/
/usr/share/icons/hicolor/256x256/apps/xmrigui.png
/usr/share/applications/xmrigui.desktop
