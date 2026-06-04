# =============================================================================
# iCross Agent — Create Desktop Shortcut
# =============================================================================
# Run this script to create a desktop shortcut that launches iCross Agent.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/create_shortcut.ps1
# =============================================================================

$ProjectDir = Split-Path -Parent $PSScriptRoot
$StartScript = Join-Path $ProjectDir "start.bat"
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $DesktopPath "iCross Agent.lnk"

# Check start.bat exists
if (-not (Test-Path $StartScript)) {
    Write-Host "[fail] start.bat not found at: $StartScript" -ForegroundColor Red
    exit 1
}

# Create WScript Shell COM object
$WScript = New-Object -ComObject WScript.Shell
$Shortcut = $WScript.CreateShortcut($ShortcutPath)

$Shortcut.TargetPath = $StartScript
$Shortcut.WorkingDirectory = $ProjectDir
$Shortcut.Description = "iCross Agent — AI-powered Ozon e-commerce operations system"
$Shortcut.WindowStyle = 7  # Minimized

# Try to find a Python icon or use a generic one
$PythonExe = Get-Command python -ErrorAction SilentlyContinue
if ($PythonExe) {
    # Use Python's icon as a proxy
    $Shortcut.IconLocation = "$($PythonExe.Source), 0"
}

$Shortcut.Save()

if (Test-Path $ShortcutPath) {
    Write-Host "[ok] 桌面快捷方式已创建: $ShortcutPath" -ForegroundColor Green
    Write-Host ""
    Write-Host "双击桌面 'iCross Agent' 快捷方式启动系统。" -ForegroundColor Cyan
    Write-Host "启动后访问: http://localhost:3000" -ForegroundColor Cyan
} else {
    Write-Host "[fail] 快捷方式创建失败" -ForegroundColor Red
}
