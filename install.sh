#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
APP_MENU_DIR="$HOME/.local/share/applications"

mkdir -p "$BIN_DIR" "$APP_MENU_DIR"

cp "$APP_DIR/ffmpeg_gui.py" "$BIN_DIR/ffmpeg-gui"
chmod +x "$BIN_DIR/ffmpeg-gui"

cat > "$APP_MENU_DIR/ffmpeg-gui.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=FFmpeg GUI
Comment=Interfaz ligera en Tkinter para FFmpeg
Exec=$BIN_DIR/ffmpeg-gui
Icon=video-x-generic
Terminal=false
Categories=AudioVideo;Video;AudioVideoEditing;
EOF

echo "Instalado correctamente en $BIN_DIR/ffmpeg-gui"
if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "Aviso: 'ffmpeg' no esta en tu PATH. Instalalo antes de usar la GUI."
fi
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo "Nota: agrega '$BIN_DIR' a tu PATH para ejecutar 'ffmpeg-gui' desde la terminal."
fi
