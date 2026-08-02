# 电信客服 Agent v1 — 后端 uvicorn 手动启动脚本（Windows）
#
# 对应：ADR 0006（uvicorn 单进程，手动启动不自启）/ F0 循环7（issue #2 验收 7）
#
# 职责：拉起 uvicorn 服务于 127.0.0.1:8000，供 nginx 反代对外。
# 不自启、不守护；进程崩溃需人工重新执行本脚本（ADR 0006 Consequences）。
#
# 用法（任一位置）：
#   powershell -ExecutionPolicy Bypass -File deploy/start_backend.ps1
#
# 前置（首次或迁移变更后手动执行一次）：
#   cd backend
#   uv run alembic upgrade head

#Requires -Version 5.1
$ErrorActionPreference = "Stop"

# 定位仓库根（脚本位于 <repo>/deploy/）
$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
Set-Location $backendDir

Write-Host "==> Starting uvicorn on 127.0.0.1:8000 (app.main:app)" -ForegroundColor Cyan
Write-Host "    提示：首次启动前请先手动执行  uv run alembic upgrade head" -ForegroundColor DarkGray
Write-Host "    提示：nginx 已就绪时，访问 http://localhost (用户端) / http://localhost:8081 (坐席台)" -ForegroundColor DarkGray

# uvicorn 单进程，仅绑定本机回环（对外由 nginx 反代）
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
