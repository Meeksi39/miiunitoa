#!/usr/bin/env bash
#
# install.sh — link this repo's files into the locations GNOME and your
# shell expect, so the repo stays the single source of truth.
#
#   ./install.sh            symlink the CLI + extension into place
#   ./install.sh --copy     copy instead of symlink (e.g. for a release)
#   ./install.sh --uninstall remove the symlinks/copies this script created
#
# Symlinking (the default) means edits in the repo take effect immediately:
# just re-run `monitor-layout` or re-enable the extension.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BIN_SRC="$REPO/bin/monitor-layout"
BIN_DST="$HOME/.local/bin/monitor-layout"
ALIAS_DST="$HOME/.local/bin/ml"

EXT_SRC="$REPO/extension/miiunitoa@meeksi39"
EXT_DST="$HOME/.local/share/gnome-shell/extensions/miiunitoa@meeksi39"

MODE="symlink"
case "${1:-}" in
  --copy)      MODE="copy" ;;
  --uninstall) MODE="uninstall" ;;
  "")          ;;
  *) echo "Unknown option: $1" >&2; exit 1 ;;
esac

backup() {
  # Back up a real (non-symlink) file/dir before we replace it.
  local path="$1"
  if [[ -e "$path" && ! -L "$path" ]]; then
    local bak="$path.bak.$(date +%s)"
    echo "  backing up existing $path -> $bak"
    mv "$path" "$bak"
  else
    rm -rf "$path"
  fi
}

link_or_copy() {
  local src="$1" dst="$2"
  mkdir -p "$(dirname "$dst")"
  backup "$dst"
  if [[ "$MODE" == "copy" ]]; then
    cp -r "$src" "$dst"
    echo "  copied  $dst"
  else
    ln -s "$src" "$dst"
    echo "  linked  $dst -> $src"
  fi
}

if [[ "$MODE" == "uninstall" ]]; then
  echo "Removing installed files..."
  for p in "$BIN_DST" "$ALIAS_DST" "$EXT_DST"; do
    if [[ -L "$p" || -e "$p" ]]; then
      rm -rf "$p"
      echo "  removed $p"
    fi
  done
  echo "Done. Saved layouts in ~/.config/monitor-layouts were left untouched."
  echo "Disable the extension with: gnome-extensions disable miiunitoa@meeksi39"
  exit 0
fi

echo "Installing monitor-layout ($MODE) from $REPO ..."

# CLI
link_or_copy "$BIN_SRC" "$BIN_DST"
# `ml` short alias -> monitor-layout
rm -f "$ALIAS_DST"
ln -s "$BIN_DST" "$ALIAS_DST"
echo "  linked  $ALIAS_DST -> $BIN_DST"

# GNOME Shell extension
link_or_copy "$EXT_SRC" "$EXT_DST"

# Compile the extension's GSettings schema so GNOME can load its settings
# (auto-switch toggle, default layout, cycle keybinding).
if command -v glib-compile-schemas >/dev/null && [[ -d "$EXT_DST/schemas" ]]; then
  glib-compile-schemas "$EXT_DST/schemas"
  echo "  compiled $EXT_DST/schemas/gschemas.compiled"
fi

echo
echo "Done."
echo "Make sure ~/.local/bin is on your PATH, then:"
echo "  gnome-extensions enable miiunitoa@meeksi39"
echo "  # Wayland: log out / back in to load the extension."
