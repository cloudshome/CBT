#!/bin/sh
# Build an unsigned .deb of the current tree into dist/.
# Signing is P22 / the release environment — this script never embeds a key.
set -eu
ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
VERSION="${SKY_DEB_VERSION:-2.35.0}"
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/sky-deb.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT

DEST="$STAGE/opt/sky"
mkdir -p "$DEST" "$STAGE/etc/sky" "$STAGE/var/lib/sky/store" "$STAGE/var/lib/sky/backups"
mkdir -p "$STAGE/lib/systemd/system" "$STAGE/DEBIAN" "$STAGE/usr/bin"

# Application tree — skip venvs, tests caches, git.
tar -C "$ROOT" \
  --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
  --exclude='.pytest_cache' --exclude='data/store' --exclude='data/store_demo' \
  --exclude='*.db' --exclude='dist' --exclude='moon' \
  -cf - . | tar -C "$DEST" -xf -

cp "$ROOT/ops/systemd/sky-"*.service "$ROOT/ops/systemd/sky-"*.timer \
  "$STAGE/lib/systemd/system/"
install -m 0755 "$ROOT/packaging/sky" "$STAGE/usr/bin/sky"

SIZE_KB=$(du -sk "$STAGE" | awk '{print $1}')
sed -e "s/^Architecture:.*/Architecture: all/" \
    "$ROOT/packaging/debian/control" | awk '
  /^Package:/ {p=1}
  p {print}
  /^$/ && p {exit}
' > "$STAGE/DEBIAN/control"
{
  echo "Version: ${VERSION}-1"
  echo "Installed-Size: ${SIZE_KB}"
} >> "$STAGE/DEBIAN/control"
install -m 0755 "$ROOT/packaging/debian/postinst" "$STAGE/DEBIAN/postinst"
install -m 0755 "$ROOT/packaging/debian/prerm" "$STAGE/DEBIAN/prerm"
install -m 0755 "$ROOT/packaging/debian/postrm" "$STAGE/DEBIAN/postrm"

mkdir -p "$ROOT/dist"
OUT="$ROOT/dist/sky-hub_${VERSION}-1_all.deb"
if command -v dpkg-deb >/dev/null 2>&1; then
  dpkg-deb --build "$STAGE" "$OUT"
  (cd "$ROOT/dist" && sha256sum "$(basename "$OUT")" > "$(basename "$OUT").sha256")
  echo "built $OUT (unsigned — sign in the release environment)"
else
  echo "dpkg-deb not installed; staged tree at $STAGE would become $OUT" >&2
  echo "install dpkg-dev on Ubuntu to produce the artifact" >&2
  exit 2
fi
