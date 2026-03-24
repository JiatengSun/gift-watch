#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

ENV_FILE="${1:-.env-lqx}"
PORT="${2:-9999}"
SAFE_NAME="$(printf '%s' "${ENV_FILE}" | tr -c '[:alnum:]._-' '_')"

mkdir -p logs run

PID_FILE="run/web.portal.${SAFE_NAME}.${PORT}.pid"
LOG_FILE="logs/web.portal.${SAFE_NAME}.${PORT}.log"

if [[ -f "${PID_FILE}" ]]; then
  EXISTING_PID="$(cat "${PID_FILE}")"
  if [[ -n "${EXISTING_PID}" ]] && kill -0 "${EXISTING_PID}" 2>/dev/null; then
    echo "web portal 已在运行: PID=${EXISTING_PID} ENV=${ENV_FILE} PORT=${PORT}"
    echo "log: ${LOG_FILE}"
    exit 0
  fi
  rm -f "${PID_FILE}"
fi

nohup python -X utf8 -m uvicorn web.app:app \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --env-file "${ENV_FILE}" \
  > "${LOG_FILE}" 2>&1 < /dev/null &

PID=$!
echo "${PID}" > "${PID_FILE}"

echo "web portal 已启动: PID=${PID}"
echo "env file: ${ENV_FILE}"
echo "port: ${PORT}"
echo "log: ${LOG_FILE}"
echo "pid file: ${PID_FILE}"
