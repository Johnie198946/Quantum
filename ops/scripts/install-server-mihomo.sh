#!/usr/bin/env bash
set -euo pipefail

VERSION="1.19.31"
SHA256="d5e74bbddbdfff49a1aef7775bf5911da59f0d7196ed509a0ac914b3653dd5f1"
URL="https://github.com/MetaCubeX/mihomo/releases/download/v${VERSION}/mihomo-linux-amd64-v${VERSION}.gz"
CONFIG="${1:-/etc/mihomo/config.yaml}"
UNIT_SOURCE="$(cd "$(dirname "$0")/../systemd" && pwd)/mihomo.service"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

[ "$(id -u)" -eq 0 ] || { echo "ERROR: run as root" >&2; exit 1; }
[ -f "$CONFIG" ] && [ ! -L "$CONFIG" ] || { echo "ERROR: missing regular config: $CONFIG" >&2; exit 1; }
[ "$(uname -m)" = "x86_64" ] || { echo "ERROR: unsupported architecture" >&2; exit 1; }

curl --fail --location --silent --show-error --connect-timeout 10 --max-time 180 "$URL" -o "$TMP/mihomo.gz"
printf '%s  %s\n' "$SHA256" "$TMP/mihomo.gz" | sha256sum --check --status
gzip -dc "$TMP/mihomo.gz" > "$TMP/mihomo"
chmod 0755 "$TMP/mihomo"
"$TMP/mihomo" -v | grep -F "v${VERSION}" >/dev/null

getent group mihomo >/dev/null || groupadd --system mihomo
id -u mihomo >/dev/null 2>&1 || useradd --system --gid mihomo --home-dir /var/lib/mihomo --shell /usr/sbin/nologin mihomo
install -d -o root -g mihomo -m 0750 /etc/mihomo
install -d -o mihomo -g mihomo -m 0750 /var/lib/mihomo
chown root:mihomo "$CONFIG"
chmod 0640 "$CONFIG"
install -o root -g root -m 0755 "$TMP/mihomo" /usr/local/bin/mihomo
install -o root -g root -m 0644 "$UNIT_SOURCE" /etc/systemd/system/mihomo.service

/usr/local/bin/mihomo -t -d /var/lib/mihomo -f "$CONFIG"
systemctl daemon-reload
systemctl enable --now mihomo.service
systemctl is-active --quiet mihomo.service
ss -lntp | grep -F '127.0.0.1:7890' >/dev/null
