# ReviewLens 一键开发启动脚本（Windows / PowerShell）
#
# 启动：Docker 基础设施 → backend(:8000) → nlp(:8100) → frontend(:5173) → worker
# 日志写入 .workbuddy/logs/ 目录。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File scripts/dev_start.ps1
#
# 注意：worker 必须启动，否则导入/推理/告警定时任务都不会执行。

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Root '.workbuddy\logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Test-Port([int]$Port) {
  $conn = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
  return $null -ne $conn
}

# ---------- 端口预检 ----------
$services = @(
  @{ Name = 'backend'; Port = 8000 },
  @{ Name = 'nlp';     Port = 8100 },
  @{ Name = 'frontend'; Port = 5173 }
)
foreach ($svc in $services) {
  if (Test-Port $svc.Port) {
    Write-Host "[WARN] $($svc.Name) 端口 $($svc.Port) 已被占用，跳过启动。" -ForegroundColor Yellow
    $svc.Skip = $true
  } else {
    $svc.Skip = $false
  }
}

# ---------- 1. Docker 基础设施 ----------
Write-Host "[1/5] 启动 Docker 基础设施..." -ForegroundColor Cyan
docker compose -f (Join-Path $Root 'docker\docker-compose.yml') up -d

# ---------- 2. backend ----------
$backend = $services | Where-Object { $_.Name -eq 'backend' }
if (-not $backend.Skip) {
  Write-Host "[2/5] 启动 backend :8000 ..." -ForegroundColor Cyan
  $py = Join-Path $Root '.venv\Scripts\python.exe'
  Start-Process -FilePath $py -ArgumentList @('-m','uvicorn','app.main:app','--reload','--port','8000') `
    -WorkingDirectory (Join-Path $Root 'backend') `
    -RedirectStandardOutput (Join-Path $LogDir 'backend.log') `
    -RedirectStandardError (Join-Path $LogDir 'backend.err.log') -WindowStyle Hidden
}

# ---------- 3. nlp ----------
$nlp = $services | Where-Object { $_.Name -eq 'nlp' }
if (-not $nlp.Skip) {
  Write-Host "[3/5] 启动 nlp :8100 ..." -ForegroundColor Cyan
  $py = Join-Path $Root '.venv\Scripts\python.exe'
  Start-Process -FilePath $py -ArgumentList @('-m','uvicorn','app.main:app','--reload','--port','8100') `
    -WorkingDirectory (Join-Path $Root 'nlp') `
    -RedirectStandardOutput (Join-Path $LogDir 'nlp.log') `
    -RedirectStandardError (Join-Path $LogDir 'nlp.err.log') -WindowStyle Hidden
}

# ---------- 4. frontend ----------
$frontend = $services | Where-Object { $_.Name -eq 'frontend' }
if (-not $frontend.Skip) {
  Write-Host "[4/5] 启动 frontend :5173 ..." -ForegroundColor Cyan
  Start-Process -FilePath 'npm.cmd' -ArgumentList @('run','dev') `
    -WorkingDirectory (Join-Path $Root 'frontend') `
    -RedirectStandardOutput (Join-Path $LogDir 'frontend.log') `
    -RedirectStandardError (Join-Path $LogDir 'frontend.err.log') -WindowStyle Hidden
}

# ---------- 5. worker ----------
Write-Host "[5/5] 启动 ARQ worker ..." -ForegroundColor Cyan
$py = Join-Path $Root '.venv\Scripts\python.exe'
Start-Process -FilePath $py -ArgumentList @('-m','app.worker') `
  -WorkingDirectory (Join-Path $Root 'backend') `
  -RedirectStandardOutput (Join-Path $LogDir 'worker.log') `
  -RedirectStandardError (Join-Path $LogDir 'worker.err.log') -WindowStyle Hidden

Write-Host ""
Write-Host "全部服务已启动（或已存在）。访问：http://localhost:5173" -ForegroundColor Green
Write-Host "日志目录：$LogDir" -ForegroundColor Green
Write-Host "停止服务：直接关闭对应进程，或参考 README 中的清理说明。" -ForegroundColor Green
