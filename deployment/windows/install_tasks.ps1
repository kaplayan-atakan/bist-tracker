# BIST Bot Windows Kurulum Scripti
# Bu script botları Windows Görev Zamanlayıcısı'na (Task Scheduler) ekler.
# Bilgisayar açıldığında otomatik olarak arka planda çalışırlar.

$ErrorActionPreference = "Stop"

# Yollar
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Resolve-Path "$ScriptDir\..\.."
$PmrBat = "$ScriptDir\start_pmr.bat"
$TradingBat = "$ScriptDir\start_trading_bot.bat"

Write-Host "BIST Bot Windows Kurulumu" -ForegroundColor Cyan
Write-Host "Proje Dizini: $ProjectRoot"
Write-Host "--------------------------------"

# Log klasörünü oluştur
$LogDir = "$ProjectRoot\logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
    Write-Host "Log klasörü oluşturuldu: $LogDir" -ForegroundColor Green
}

# 1. PMR Bot Görevi
$PmrTaskName = "BIST_PMR_Bot"
Write-Host "Görev oluşturuluyor: $PmrTaskName..."

$PmrAction = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$PmrBat`"" -WorkingDirectory $ProjectRoot
$PmrTrigger = New-ScheduledTaskTrigger -AtLogon
$PmrSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Days 365) -Hidden

try {
    Unregister-ScheduledTask -TaskName $PmrTaskName -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -Action $PmrAction -Trigger $PmrTrigger -Settings $PmrSettings -TaskName $PmrTaskName -Description "BIST Pre-Manipulation Radar Bot" | Out-Null
    Write-Host "✅ $PmrTaskName başarıyla kuruldu." -ForegroundColor Green
}
catch {
    Write-Host "❌ $PmrTaskName kurulamadı: $_" -ForegroundColor Red
}

# 2. Trading Bot Görevi
$TradingTaskName = "BIST_Trading_Bot"
Write-Host "Görev oluşturuluyor: $TradingTaskName..."

$TradingAction = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$TradingBat`"" -WorkingDirectory "$ProjectRoot\core-src"
$TradingTrigger = New-ScheduledTaskTrigger -AtLogon
$TradingSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Days 365) -Hidden

try {
    Unregister-ScheduledTask -TaskName $TradingTaskName -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -Action $TradingAction -Trigger $TradingTrigger -Settings $TradingSettings -TaskName $TradingTaskName -Description "BIST Main Trading Bot" | Out-Null
    Write-Host "✅ $TradingTaskName başarıyla kuruldu." -ForegroundColor Green
}
catch {
    Write-Host "❌ $TradingTaskName kurulamadı: $_" -ForegroundColor Red
}

Write-Host "--------------------------------"
Write-Host "Kurulum tamamlandı!"
Write-Host "Botlar bilgisayarınıza giriş yaptığınızda otomatik başlayacaktır."
Write-Host "Hemen başlatmak için Görev Zamanlayıcısı'nı açın veya bilgisayarı yeniden başlatın."
Write-Host "Logları takip etmek için: $LogDir"
