#!/usr/bin/env bash
# Installs BS Mods for this user: a private Python environment with PyQt6 in
# ~/.local/share/bsmods/venv, the "bsmods" command and a launcher entry. No sudo needed.
#   ./install.sh              install or update
#   ./install.sh --uninstall  remove it (your mods stay where they are)
set -euo pipefail
cd "$(dirname "$0")"

DIR="${XDG_DATA_HOME:-$HOME/.local/share}/bsmods"
BIN="$HOME/.local/bin"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

if [ "${1:-}" = "--uninstall" ]; then
    rm -rf "$DIR/app" "$DIR/venv" "$BIN/bsmods" "$APPS/bsmods.desktop"
    echo "BS Mods removed. Mods turned off are still in $DIR/disabled"
    exit 0
fi

command -v python3 >/dev/null || { echo "python3 is needed" >&2; exit 1; }
command -v bsdtar >/dev/null || echo "note: install libarchive (bsdtar) to unpack mod archives" >&2

mkdir -p "$DIR/app" "$BIN" "$APPS"
[ -x "$DIR/venv/bin/python" ] || python3 -m venv "$DIR/venv"
"$DIR/venv/bin/python" -m pip install -q --upgrade pip PyQt6
cp bsmods.py bsmods.svg "$DIR/app/"

cat > "$BIN/bsmods" <<EOS
#!/usr/bin/env bash
exec "$DIR/venv/bin/python" "$DIR/app/bsmods.py" "\$@"
EOS
chmod +x "$BIN/bsmods"

cat > "$APPS/bsmods.desktop" <<EOS
[Desktop Entry]
Type=Application
Name=BS Mods
GenericName=Blade & Sorcery mod manager
Comment=Install, turn on/off and remove Blade & Sorcery mods
Exec="$BIN/bsmods" %F
Icon=$DIR/app/bsmods.svg
Terminal=false
Categories=Game;Utility;
Keywords=blade;sorcery;mods;nexus;vr;
StartupWMClass=bsmods
EOS
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" >/dev/null 2>&1 || true
echo "BS Mods installed: open it from your app launcher, or run bsmods"
