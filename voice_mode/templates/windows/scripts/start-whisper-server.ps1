# Whisper service startup script (Windows).
# Run by a Task Scheduler task. Mirrors start-whisper-server.sh.
# Layout: <base>\services\whisper\bin\start-whisper-server.ps1, where <base> is
# ~\.voicemode (user scope) or %ProgramData%\VoiceMode (machine scope).

$ErrorActionPreference = 'Continue'

$WhisperDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Base = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$LogDir = Join-Path $Base 'logs\whisper'
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

function Expand-HomePath([string]$Path) {
    if ($Path -eq '~' -or $Path.StartsWith('~/') -or $Path.StartsWith('~\')) {
        return (Join-Path $env:USERPROFILE $Path.Substring(1).TrimStart('/', '\'))
    }
    return $Path
}

Import-VoiceModeEnv (Join-Path $Base 'voicemode.env')

$Port = Get-Setting 'VOICEMODE_WHISPER_PORT' '2022'
$Model = Get-Setting 'VOICEMODE_WHISPER_MODEL' 'base'
$Threads = Get-Setting 'VOICEMODE_WHISPER_THREADS' ([string][Environment]::ProcessorCount)
$BindHost = Get-Setting 'VOICEMODE_WHISPER_HOST' '127.0.0.1'
$ModelDir = Expand-HomePath (Get-Setting 'VOICEMODE_WHISPER_MODEL_PATH' (Join-Path $WhisperDir 'models'))
$ModelFile = Join-Path $ModelDir "ggml-$Model.bin"
$Server = Join-Path $WhisperDir 'bin\whisper-server.exe'

# ffmpeg is required by --convert. Machine-scope tasks run as SYSTEM and do not
# see user PATH entries, so also look in the shared bin directories.
$env:PATH = (@((Join-Path $Base 'bin'), (Join-Path $WhisperDir 'bin')) + @($env:PATH)) -join ';'

if (-not (Test-Path -LiteralPath $Server)) { Write-Log "whisper-server.exe not found at $Server"; exit 1 }
if (-not (Test-Path -LiteralPath $ModelFile)) { Write-Log "Model not found: $ModelFile"; exit 1 }

Write-Log "Starting whisper-server (model=$Model port=$Port threads=$Threads host=$BindHost)"

# whisper-server writes temp files next to its working directory for --convert.
$WorkDir = Join-Path $WhisperDir 'tmp'
New-Item -ItemType Directory -Force $WorkDir | Out-Null

$ArgumentList = @(
    '--model', ('"{0}"' -f $ModelFile),
    '--host', $BindHost,
    '--port', $Port,
    '--threads', $Threads,
    '--inference-path', '/v1/audio/transcriptions',
    '--convert'
) -join ' '

$Process = Start-Process -FilePath $Server -ArgumentList $ArgumentList -WorkingDirectory $WorkDir `
    -NoNewWindow -Wait -PassThru `
    -RedirectStandardOutput (Join-Path $LogDir 'whisper.out.log') `
    -RedirectStandardError (Join-Path $LogDir 'whisper.err.log')
Write-Log "whisper-server exited with code $($Process.ExitCode)"
exit $Process.ExitCode
