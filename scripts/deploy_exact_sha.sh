#!/bin/bash
# 从本地已审查的 Git commit 导出并执行目标 SHA 的服务器部署脚本。
# 用法: AI_LAB_DEPLOY_HOST=root@example.com bash scripts/deploy_exact_sha.sh <40位 commit SHA>

set -euo pipefail

if [ "$#" -ne 1 ] || [[ ! "$1" =~ ^[0-9a-fA-F]{40}$ ]]; then
  echo "ERROR: 必须提供且仅提供一个精确的 40 位 commit SHA" >&2
  exit 2
fi

EXPECTED_SHA="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
DEPLOY_HOST="${AI_LAB_DEPLOY_HOST:?ERROR: 必须设置 AI_LAB_DEPLOY_HOST}"
REMOTE_SUDO="${AI_LAB_DEPLOY_REMOTE_SUDO:-0}"
IDENTITY_FILE="${AI_LAB_DEPLOY_IDENTITY_FILE:-}"
KNOWN_HOSTS_FILE="${AI_LAB_DEPLOY_KNOWN_HOSTS_FILE:?ERROR: 必须设置 AI_LAB_DEPLOY_KNOWN_HOSTS_FILE}"
EXPECTED_CURRENT_SHA="${AI_LAB_EXPECTED_CURRENT_SHA:?ERROR: 必须设置 AI_LAB_EXPECTED_CURRENT_SHA}"
SSH_OPTIONS=(-F /dev/null -o BatchMode=yes)
SCP_OPTIONS=(-q -F /dev/null -o BatchMode=yes)
if [ -n "$IDENTITY_FILE" ]; then
  if [ ! -f "$IDENTITY_FILE" ]; then
    echo "ERROR: AI_LAB_DEPLOY_IDENTITY_FILE does not exist" >&2
    exit 2
  fi
  SSH_OPTIONS+=(-o IdentitiesOnly=yes -i "$IDENTITY_FILE")
  SCP_OPTIONS+=(-o IdentitiesOnly=yes -i "$IDENTITY_FILE")
fi
if [ ! -f "$KNOWN_HOSTS_FILE" ]; then
  echo "ERROR: AI_LAB_DEPLOY_KNOWN_HOSTS_FILE does not exist" >&2
  exit 2
fi
SSH_OPTIONS+=(-o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$KNOWN_HOSTS_FILE")
SCP_OPTIONS+=(-o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$KNOWN_HOSTS_FILE")
if [[ ! "$REMOTE_SUDO" =~ ^[01]$ ]]; then
  echo "ERROR: AI_LAB_DEPLOY_REMOTE_SUDO must be 0 or 1" >&2
  exit 2
fi
if [[ ! "$EXPECTED_CURRENT_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "ERROR: AI_LAB_EXPECTED_CURRENT_SHA must be a lowercase 40-character SHA" >&2
  exit 2
fi
LOCAL_SCRIPT="$(mktemp "${TMPDIR:-/tmp}/ai-lab-update.XXXXXX")"
LOCAL_SOURCE="$(mktemp "${TMPDIR:-/tmp}/ai-lab-source.XXXXXX.tar.gz")"
REMOTE_SCRIPT=""
REMOTE_SOURCE="/opt/ai-lab-shared/offline-source/ai-lab-platform-$EXPECTED_SHA.tar.gz"

cleanup() {
  rc=$?
  trap - EXIT
  rm -f "$LOCAL_SCRIPT" "$LOCAL_SOURCE"
  if [[ "$REMOTE_SCRIPT" =~ ^/tmp/ai-lab-update\.[A-Za-z0-9]{6}$ ]]; then
    ssh "${SSH_OPTIONS[@]}" "$DEPLOY_HOST" rm -f -- "$REMOTE_SCRIPT" >/dev/null 2>&1 || true
  fi
  ssh "${SSH_OPTIONS[@]}" "$DEPLOY_HOST" rm -f -- "$REMOTE_SOURCE" >/dev/null 2>&1 || true
  exit "$rc"
}
trap cleanup EXIT

git cat-file -e "$EXPECTED_SHA^{commit}"
git show "$EXPECTED_SHA:scripts/update.sh" > "$LOCAL_SCRIPT"
bash -n "$LOCAL_SCRIPT"
LOCAL_HASH="$(shasum -a 256 "$LOCAL_SCRIPT" | cut -d' ' -f1)"
git archive --format=tar --prefix="ai-lab-platform-$EXPECTED_SHA/" "$EXPECTED_SHA" | gzip -n > "$LOCAL_SOURCE"
SOURCE_HASH="$(shasum -a 256 "$LOCAL_SOURCE" | cut -d' ' -f1)"

REMOTE_SCRIPT="$(ssh "${SSH_OPTIONS[@]}" "$DEPLOY_HOST" mktemp /tmp/ai-lab-update.XXXXXX)"
if [[ ! "$REMOTE_SCRIPT" =~ ^/tmp/ai-lab-update\.[A-Za-z0-9]{6}$ ]]; then
  echo "ERROR: 远端未返回受控的随机临时路径" >&2
  exit 1
fi

scp "${SCP_OPTIONS[@]}" "$LOCAL_SCRIPT" "$DEPLOY_HOST:$REMOTE_SCRIPT"
ssh "${SSH_OPTIONS[@]}" "$DEPLOY_HOST" install -d -o root -g root -m 0755 /opt/ai-lab-shared/offline-source
scp "${SCP_OPTIONS[@]}" "$LOCAL_SOURCE" "$DEPLOY_HOST:$REMOTE_SOURCE.upload"
ssh "${SSH_OPTIONS[@]}" "$DEPLOY_HOST" install -o root -g root -m 0600 \
  "$REMOTE_SOURCE.upload" "$REMOTE_SOURCE"
ssh "${SSH_OPTIONS[@]}" "$DEPLOY_HOST" rm -f -- "$REMOTE_SOURCE.upload"
ssh "${SSH_OPTIONS[@]}" "$DEPLOY_HOST" bash -s -- \
  "$REMOTE_SCRIPT" "$EXPECTED_SHA" "$LOCAL_HASH" "$REMOTE_SUDO" \
  "$REMOTE_SOURCE" "$SOURCE_HASH" "$EXPECTED_CURRENT_SHA" <<'REMOTE'
set -euo pipefail
REMOTE_SCRIPT="$1"
EXPECTED_SHA="$2"
LOCAL_HASH="$3"
REMOTE_SUDO="$4"
REMOTE_SOURCE="$5"
SOURCE_HASH="$6"
EXPECTED_CURRENT_SHA="$7"
REMOTE_HASH="$(sha256sum "$REMOTE_SCRIPT" | cut -d' ' -f1)"
test "$REMOTE_HASH" = "$LOCAL_HASH"
if [ "$REMOTE_SUDO" = "1" ]; then
  sudo -n env AI_LAB_EXPECTED_CURRENT_SHA="$EXPECTED_CURRENT_SHA" \
    AI_LAB_SOURCE_ARCHIVE="$REMOTE_SOURCE" \
    AI_LAB_SOURCE_ARCHIVE_SHA256="$SOURCE_HASH" bash "$REMOTE_SCRIPT" "$EXPECTED_SHA"
else
  AI_LAB_EXPECTED_CURRENT_SHA="$EXPECTED_CURRENT_SHA" \
    AI_LAB_SOURCE_ARCHIVE="$REMOTE_SOURCE" AI_LAB_SOURCE_ARCHIVE_SHA256="$SOURCE_HASH" \
    bash "$REMOTE_SCRIPT" "$EXPECTED_SHA"
fi
REMOTE
