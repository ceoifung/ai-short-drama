# Bootstrap: 用已有 Python 建虚拟环境(绝不安装 Python)。用法:
#   powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$script = Join-Path $PSScriptRoot ".agents\skills\ai-short-drama\scripts\setup_env.py"
if (-not (Test-Path $script)) { Write-Host "[x] 找不到 setup_env.py, 请确认仓库完整" -ForegroundColor Red; exit 1 }

$cmd = $null; $pre = @()
if (Get-Command py -ErrorAction SilentlyContinue) { $cmd = "py"; $pre = @("-3") }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $cmd = "python" }

if ($null -eq $cmd) {
  Write-Host "[x] 未检测到 Python。本脚本不会替你安装 Python, 请先装好再重跑本脚本:" -ForegroundColor Red
  Write-Host "    winget install Python.Python.3.12"
  Write-Host "    或 www.python.org 下载安装(勾选 Add to PATH)"
  exit 1
}

Write-Host "[ok] 使用已有 Python: $cmd $($pre -join ' ')"
& $cmd @pre $script @args
exit $LASTEXITCODE
