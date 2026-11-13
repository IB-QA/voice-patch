# Kokoro TTS service startup script (Windows).
# Run by a Task Scheduler task. Mirrors the Kokoro-FastAPI start-cpu script but
# uses the service's own virtual environment and a bundled eSpeak NG, so no
# machine-wide install is needed.
# Layout: <base>\services\kokoro\start-kokoro.ps1 (script sits in the repo root).

$ErrorActionPreference = 'Continue'

$KokoroDir = (Resolve-Path $PSScriptRoot).Path
$Base = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$LogDir = Join-Path $Base 'logs\kokoro'
New-Item -ItemType Directory -Force $LogDir | Out-Null
$StartupLog = Join-Path $LogDir 'startup.log'

function Write-Log([string]$Message) {
    "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message | Add-Content -Path $StartupLog
}

# >>> Import-VoiceModeEnv: load KEY=VALUE pairs from voicemode.env as INERT DATA >>>
# Never evaluate values (no Invoke-Expression, no ExpandString). Mirrors the
# bash voicemode_load_env_file hardening (GHSA-h97v-r3jw-cf6f).
function Import-VoiceModeEnv([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        $line = $line.Trim()
        if (-not $line -or $line.StartsWith('#')) { continue }
        if ($line -notmatch '^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { continue }
        $value = $Matches[2].Trim()
        if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($Matches[1], $value, 'Process')
    }
}
# <<< Import-VoiceModeEnv <<<

function Get-Setting([string]$Name, [string]$Default) {
    $value = [Environment]::GetEnvironmentVariable($Name, 'Process')
    if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
    return $value
}

Import-VoiceModeEnv (Join-Path $Base 'voicemode.env')

$Port = Get-Setting 'VOICEMODE_KOKORO_PORT' '8880'
$BindHost = Get-Setting 'VOICEMODE_KOKORO_HOST' '127.0.0.1'
$Python = Join-Path $KokoroDir '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $Python)) { Write-Log "Kokoro virtual environment missing: $Python"; exit 1 }

$env:PYTHONUTF8 = '1'
$env:PROJECT_ROOT = $KokoroDir
$DeviceFile = Join-Path $KokoroDir '.device'
$Device = Get-Setting 'VOICEMODE_KOKORO_DEVICE' ''
if (-not $Device -and (Test-Path -LiteralPath $DeviceFile)) { $Device = (Get-Content -LiteralPath $DeviceFile -Raw).Trim() }
$env:USE_GPU = if ($Device -eq 'gpu') { 'true' } else { 'false' }
$env:PYTHONPATH = "$KokoroDir;$KokoroDir\api"
$env:MODEL_DIR = 'src/models'
$env:VOICES_DIR = 'src/voices/v1_0'
$env:WEB_PLAYER_PATH = "$KokoroDir/web"

# eSpeak NG ships inside the venv via espeakng-loader.
$env:PHONEMIZER_ESPEAK_LIBRARY = (& $Python -c 'import espeakng_loader as e; print(e.get_library_path())')
$env:PHONEMIZER_ESPEAK_PATH = (& $Python -c 'import espeakng_loader as e; print(e.get_data_path())')
$env:ESPEAKNG_DATA_PATH = $env:PHONEMIZER_ESPEAK_PATH

Set-Location $KokoroDir
Write-Log "Starting Kokoro (host=$BindHost port=$Port)"

$ArgumentList = @('-m', 'uvicorn', 'api.src.main:app', '--host', $BindHost, '--port', $Port) -join ' '
$Process = Start-Process -FilePath $Python -ArgumentList $ArgumentList -WorkingDirectory $KokoroDir `
    -NoNewWindow -Wait -PassThru `
    -RedirectStandardOutput (Join-Path $LogDir 'kokoro.out.log') `
    -RedirectStandardError (Join-Path $LogDir 'kokoro.err.log')
Write-Log "Kokoro exited with code $($Process.ExitCode)"
exit $Process.ExitCode
