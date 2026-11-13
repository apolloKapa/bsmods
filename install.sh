#!/usr/bin/env bash
# Installs Armory for this user: a private Python environment with PyQt6 in
# ~/.local/share/armory/venv, the "armory" command and a launcher entry. No sudo needed.
#   ./install.sh              install or update
#   ./install.sh --uninstall  remove the app (your mods, profiles and downloads stay)
set -euo pipefail
cd "$(dirname "$0")"

DIR="${XDG_DATA_HOME:-$HOME/.local/share}/armory"
BIN="$HOME/.local/bin"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICONS="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"

if [ "${1:-}" = "--uninstall" ]; then
    rm -rf "$DIR/app" "$DIR/venv" "$BIN/armory" "$APPS/armory.desktop" "$APPS/armory-links.desktop" "$ICONS/armory.svg"
    echo "Armory removed. Mods, profiles and downloads are still in $DIR"
    echo "(turn mods off or use ⋯ → Take every mod out of the game first if you want games clean)"
    exit 0
fi

command -v python3 >/dev/null || { echo "python3 is needed" >&2; exit 1; }
command -v bsdtar >/dev/null || command -v 7z >/dev/null || \
    echo "note: install libarchive (bsdtar) or 7-Zip to unpack mod archives" >&2

mkdir -p "$DIR/app" "$BIN" "$APPS" "$ICONS"
[ -x "$DIR/venv/bin/python" ] || python3 -m venv "$DIR/venv"
"$DIR/venv/bin/python" -m pip install -q --upgrade pip PyQt6
rm -rf "$DIR/app/armory"
cp -r armory "$DIR/app/armory"
find "$DIR/app/armory" -name __pycache__ -prune -exec rm -rf {} +
cp armory/armory.svg "$ICONS/armory.svg"

cat > "$BIN/armory" <<EOS
#!/usr/bin/env bash
PYTHONPATH="$DIR/app" exec "$DIR/venv/bin/python" -m armory "\$@"
EOS
chmod +x "$BIN/armory"

cat > "$APPS/armory.desktop" <<EOS
[Desktop Entry]
Type=Application
Name=Armory
GenericName=Mod manager
Comment=Install, update and switch mods for your games, with Nexus Mods and Thunderstore
Exec="$BIN/armory" %U
Icon=armory
Terminal=false
Categories=Game;Utility;
Keywords=mods;modding;nexus;thunderstore;bepinex;steam;proton;
StartupWMClass=armory
EOS
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" >/dev/null 2>&1 || true
echo "Armory installed: open it from your app launcher, or run armory"
