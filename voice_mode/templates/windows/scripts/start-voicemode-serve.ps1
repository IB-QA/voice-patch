# VoiceMode HTTP server startup script (Windows). Mirrors start-voicemode-serve.sh.
# Layout: <base>\services\voicemode\bin\start-voicemode-serve.ps1

$ErrorActionPreference = 'Continue'

$Base = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$LogDir = Join-Path $Base 'logs\serve'
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

$ServeHost = Get-Setting 'VOICEMODE_SERVE_HOST' '127.0.0.1'
$ServePort = Get-Setting 'VOICEMODE_SERVE_PORT' '8765'
$Transport = Get-Setting 'VOICEMODE_SERVE_TRANSPORT' 'streamable-http'
$LogLevel = Get-Setting 'VOICEMODE_SERVE_LOG_LEVEL' 'info'

$Arguments = [System.Collections.Generic.List[string]]::new()
$Arguments.AddRange([string[]]@('serve', '--host', $ServeHost, '--port', $ServePort, '--transport', $Transport, '--log-level', $LogLevel))

if ((Get-Setting 'VOICEMODE_SERVE_ALLOW_LOCAL' 'true') -eq 'true') { $Arguments.Add('--allow-local') } else { $Arguments.Add('--no-allow-local') }
if ((Get-Setting 'VOICEMODE_SERVE_ALLOW_ANTHROPIC' 'false') -eq 'true') { $Arguments.Add('--allow-anthropic') }
if ((Get-Setting 'VOICEMODE_SERVE_ALLOW_TAILSCALE' 'false') -eq 'true') { $Arguments.Add('--allow-tailscale') }
foreach ($ip in (Get-Setting 'VOICEMODE_SERVE_ALLOWED_IPS' '').Split(',')) {
    if ($ip.Trim()) { $Arguments.Add('--allow-ip'); $Arguments.Add($ip.Trim()) }
}
$Secret = Get-Setting 'VOICEMODE_SERVE_SECRET' ''
if ($Secret) { $Arguments.Add('--secret'); $Arguments.Add($Secret) }
$Token = Get-Setting 'VOICEMODE_SERVE_TOKEN' ''
if ($Token) { $Arguments.Add('--token'); $Arguments.Add($Token) }

# The installer records the exact voicemode.exe it was run from, so the service
# runs the same code the user installed rather than whatever is first on PATH.
$Recorded = Join-Path $PSScriptRoot 'voicemode-exe.txt'
$VoiceMode = $null
if (Test-Path -LiteralPath $Recorded) { $VoiceMode = (Get-Content -LiteralPath $Recorded -TotalCount 1).Trim() }
if (-not $VoiceMode -or -not (Test-Path -LiteralPath $VoiceMode)) {
    $VoiceMode = (Get-Command voicemode.exe -ErrorAction SilentlyContinue).Source
}
if (-not $VoiceMode) { Write-Log 'voicemode.exe not found'; exit 1 }

Write-Log "Starting VoiceMode HTTP server on ${ServeHost}:${ServePort} ($Transport) using $VoiceMode"
$Process = Start-Process -FilePath $VoiceMode -ArgumentList ($Arguments -join ' ') -NoNewWindow -Wait -PassThru `
    -RedirectStandardOutput (Join-Path $LogDir 'serve.out.log') `
    -RedirectStandardError (Join-Path $LogDir 'serve.err.log')
Write-Log "VoiceMode HTTP server exited with code $($Process.ExitCode)"
exit $Process.ExitCode
