#!/usr/bin/env bash
set -euo pipefail

rm -f "$HOME/.local/bin/ffmpeg-gui"
rm -f "$HOME/.local/share/applications/ffmpeg-gui.desktop"

echo "FFmpeg GUI desinstalado de ~/.local/bin y del menu."
echo "Tus videos y ffmpeg no fueron modificados."
