.DEFAULT_GOAL := install
.PHONY: install uninstall deb rpm install-deps deb-deps rpm-deps

package = xmrigui_1.8.2_amd64
SKIP_DEPS ?= 0
SUDO ?= $(shell if [ "$$(id -u)" -ne 0 ]; then printf sudo; fi)

# Use distribution packages so the installed script works with system Python.
define install_dependencies
	@if [ "$(SKIP_DEPS)" = "1" ]; then \
		echo "Skipping dependency installation (SKIP_DEPS=1)."; \
	elif command -v apt-get >/dev/null 2>&1; then \
		$(SUDO) apt-get update && $(SUDO) apt-get install -y $(1); \
	elif command -v dnf >/dev/null 2>&1; then \
		$(SUDO) dnf install -y $(2); \
	else \
		echo "No supported package manager found (apt-get or dnf). Install dependencies manually and use SKIP_DEPS=1." >&2; \
		exit 1; \
	fi
endef

install-deps:
	$(call install_dependencies,python3 python3-pyqt6 libuv1-dev,python3 python3-qt6 libuv-devel)

deb-deps:
	$(call install_dependencies,python3 python3-pyqt6 libuv1-dev dpkg-dev,python3 python3-qt6 libuv-devel dpkg)

rpm-deps:
	$(call install_dependencies,python3 python3-pyqt6 libuv1-dev rpm,python3 python3-qt6 libuv-devel rpm-build)

install: install-deps
	mkdir -p /opt/xmrigui
	mkdir -p /usr/share/icons/hicolor/256x256/apps
	cp xmrigui.png /opt/xmrigui/
	cp xmrigui.png /usr/share/icons/hicolor/256x256/apps/
	cp xmrigui.desktop /usr/share/applications/
	cp xmrig /opt/xmrigui/
	chmod +x /opt/xmrigui/xmrig
	cp mining_tools.py /usr/local/bin/mining_tools.py
	cp xmrigui.py /usr/local/bin/xmrigui
	chmod +x /usr/local/bin/xmrigui

uninstall:
	rm /usr/local/bin/xmrigui /usr/local/bin/mining_tools.py
	rm -rf /opt/xmrigui
	rm /usr/share/icons/hicolor/256x256/apps/xmrigui.png
	rm /usr/share/applications/xmrigui.desktop

deb: deb-deps
	mkdir -p $(package)/usr/local/bin/
	mkdir -p $(package)/opt/xmrigui/
	mkdir -p $(package)/usr/share/icons/hicolor/256x256/apps/
	mkdir -p $(package)/usr/share/applications/
	cp mining_tools.py $(package)/usr/local/bin/mining_tools.py
	cp xmrigui.py $(package)/usr/local/bin/xmrigui
	chmod +x $(package)/usr/local/bin/xmrigui
	cp xmrig $(package)/opt/xmrigui/
	chmod +x $(package)/opt/xmrigui/xmrig
	cp xmrigui.png $(package)/opt/xmrigui/
	cp xmrigui.png $(package)/usr/share/icons/hicolor/256x256/apps/
	cp xmrigui.desktop $(package)/usr/share/applications/
	dpkg-deb --build --root-owner-group $(package)

rpm: rpm-deps
	mkdir -p rpmbuild/BUILD rpmbuild/RPMS rpmbuild/SOURCES rpmbuild/SPECS rpmbuild/SRPMS
	cp xmrigui.py mining_tools.py xmrig xmrigui.png xmrigui.desktop rpmbuild/SOURCES/
	cp xmrigui.spec rpmbuild/SPECS/ 2>/dev/null || true
	rpmbuild -bb --define "_topdir $(shell pwd)/rpmbuild" rpmbuild/SPECS/xmrigui.spec
	cp rpmbuild/RPMS/*/*.rpm .
	rm -rf rpmbuild
