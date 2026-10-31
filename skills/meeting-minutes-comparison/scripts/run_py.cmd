@echo off
REM AgentLoop 标准启动器：使用系统 python3（不创建 skill 本地 .venv）。
setlocal EnableDelayedExpansion
cd /d "%~dp0.."
set "ARGS=%*"

where python3 >nul 2>&1
if %ERRORLEVEL%==0 (
  python3 %ARGS%
  exit /b %ERRORLEVEL%
)

where py >nul 2>&1
if %ERRORLEVEL%==0 (
  echo [run_py] fallback: py -3 1>&2
  py -3 %ARGS%
  exit /b %ERRORLEVEL%
)

echo {"ok":false,"error":"ENV_UNSATISFIED","message":"Python 3 环境不满足：系统无 python3/py -3。请安装 Python 3 并执行 pip install -r requirements.txt"} 1>&2
exit /b 1
