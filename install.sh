#!/usr/bin/env bash
set -euo pipefail

source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
install_dir=${MOROK_INSTALL_DIR:-"$data_home/morok-assistant"}
bin_dir=${MOROK_BIN_DIR:-"$HOME/.local/bin"}
desktop_dir=${MOROK_DESKTOP_DIR:-"$data_home/applications"}
icon_dir=${MOROK_ICON_DIR:-"$data_home/icons/hicolor/256x256/apps"}
python_command=${PYTHON:-python3}

if ! command -v "$python_command" >/dev/null 2>&1; then
    echo "Для установки нужен Python 3.11 или новее." >&2
    exit 1
fi

if ! "$python_command" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
    echo "Для установки нужен Python 3.11 или новее." >&2
    exit 1
fi

mkdir -p "$install_dir" "$bin_dir" "$desktop_dir" "$icon_dir"
rm -rf "$install_dir/src" "$install_dir/README.md" "$install_dir/pyproject.toml"
cp -a "$source_dir/src" "$install_dir/src"
cp "$source_dir/pyproject.toml" "$source_dir/README.md" "$source_dir/morok-icon.png" \
    "$source_dir/install.sh" "$source_dir/uninstall.sh" "$install_dir/"

if [ ! -x "$install_dir/.venv/bin/python" ]; then
    "$python_command" -m venv "$install_dir/.venv"
fi
"$install_dir/.venv/bin/python" -m pip install --quiet --upgrade "$install_dir"

cat >"$bin_dir/morok-assistant" <<EOF
#!/usr/bin/env bash
exec "$install_dir/.venv/bin/python" -m morok_assistant "\$@"
EOF
chmod 0755 "$bin_dir/morok-assistant"

cat >"$bin_dir/morok-assistant-uninstall" <<EOF
#!/usr/bin/env bash
exec "$install_dir/uninstall.sh" "\$@"
EOF
chmod 0755 "$bin_dir/morok-assistant-uninstall"
cp "$source_dir/morok-icon.png" "$icon_dir/morok-icon.png"

cat >"$desktop_dir/morok-assistant.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Морок
Comment=Настольный помощник Морок
Exec=$bin_dir/morok-assistant
Icon=morok-icon
Terminal=false
StartupNotify=false
Categories=Utility;
EOF
chmod 0755 "$desktop_dir/morok-assistant.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$desktop_dir" >/dev/null 2>&1 || true
fi

echo "Морок установлен. Запустите его из меню приложений или командой:"
echo "  $bin_dir/morok-assistant"

if [ "${1:-}" != "--no-launch" ]; then
    "$bin_dir/morok-assistant" >/dev/null 2>&1 &
fi
