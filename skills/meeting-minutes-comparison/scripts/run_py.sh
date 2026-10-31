#!/usr/bin/env bash
# AgentLoop 标准启动器：使用系统 python3（不创建 skill 本地 .venv）。
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

_normalize_args() {
  local out=()
  local arg
  for arg in "$@"; do
    if [[ "$arg" =~ ^skills/[^/]+/(.+)$ ]]; then
      out+=("${BASH_REMATCH[1]}")
    else
      out+=("$arg")
    fi
  done
  ARGS=("${out[@]}")
}

_normalize_args "$@"

if command -v python3 >/dev/null 2>&1; then
  exec python3 "${ARGS[@]}"
fi

if command -v py >/dev/null 2>&1; then
  echo "[run_py] fallback: py -3" >&2
  exec py -3 "${ARGS[@]}"
fi

echo '{"ok":false,"error":"ENV_UNSATISFIED","message":"Python 3 环境不满足：系统无 python3。请安装 Python 3 并执行 pip3 install -r requirements.txt"}' >&2
exit 1
