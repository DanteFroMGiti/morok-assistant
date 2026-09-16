#!/usr/bin/env bash
set -euo pipefail

data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
install_dir=${MOROK_INSTALL_DIR:-"$data_home/morok-assistant"}
bin_dir=${MOROK_BIN_DIR:-"$HOME/.local/bin"}
desktop_dir=${MOROK_DESKTOP_DIR:-"$data_home/applications"}
icon_dir=${MOROK_ICON_DIR:-"$data_home/icons/hicolor/256x256/apps"}
config_home=${XDG_CONFIG_HOME:-"$HOME/.config"}

pkill -f '/morok-assistant/.venv/bin/python -m morok_assistant' 2>/dev/null || true
rm -f "$bin_dir/morok-assistant" "$bin_dir/morok-assistant-uninstall"
rm -f "$desktop_dir/morok-assistant.desktop"
rm -f "$icon_dir/morok-icon.png"
rm -f "$config_home/autostart/morok-assistant.desktop"
rm -rf "$install_dir"

if [ "${1:-}" = "--purge" ]; then
    rm -rf "$config_home/morok-assistant"
    echo "Морок и его настройки удалены."
else
    echo "Морок удалён. Настройки сохранены в $config_home/morok-assistant."
fi
