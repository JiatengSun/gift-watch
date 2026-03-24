#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

ENV_FILE="${1:-.env-lqx}"
PORT="${2:-9999}"
SAFE_NAME="$(printf '%s' "${ENV_FILE}" | tr -c '[:alnum:]._-' '_')"
PID_FILE="run/web.portal.${SAFE_NAME}.${PORT}.pid"

if [[ ! -f "${PID_FILE}" ]]; then
  echo "未找到 PID 文件: ${PID_FILE}"
  exit 0
fi

PID="$(cat "${PID_FILE}")"
if [[ -n "${PID}" ]] && kill -0 "${PID}" 2>/dev/null; then
  kill "${PID}" || true
  sleep 1
  if kill -0 "${PID}" 2>/dev/null; then
    kill -9 "${PID}" || true
  fi
  echo "web portal 已停止: PID=${PID}"
else
  echo "进程不存在，清理 PID 文件: ${PID_FILE}"
fi

rm -f "${PID_FILE}"
