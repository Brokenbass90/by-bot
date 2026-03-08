Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Import-EnvFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            return
        }

        $parts = $line.Split("=", 2)
        $key = $parts[0].Trim()
        $value = $parts[1].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($key, $value, "Process")
    }
}

function Env-OrDefault {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$DefaultValue
    )

    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($value)) {
        return $DefaultValue
    }
    return $value
}

$activatePath = Join-Path $RepoRoot ".venv\\Scripts\\Activate.ps1"
if (Test-Path -LiteralPath $activatePath) {
    . $activatePath
}

Import-EnvFile -Path (Join-Path $RepoRoot ".env")

$localEnv = $env:FOREX_MT5_LOCAL_ENV
if (-not $localEnv) {
    $repoLocal = Join-Path $RepoRoot "configs\\forex_mt5_demo_local.env"
    if (Test-Path -LiteralPath $repoLocal) {
        $localEnv = $repoLocal
    } else {
        $localEnv = Join-Path $HOME ".config\\bybit-bot\\forex_mt5_demo_local.env"
    }
}
Import-EnvFile -Path $localEnv

$argsList = @(
    "scripts/forex_mt5_demo_bridge.py",
    "--env-file", (Env-OrDefault -Name "FOREX_DEMO_ENV_FILE" -DefaultValue "docs/forex_demo_env_latest.env"),
    "--data-dir", (Env-OrDefault -Name "FOREX_DATA_DIR" -DefaultValue "data_cache/forex"),
    "--state-path", (Env-OrDefault -Name "FOREX_BRIDGE_STATE_PATH" -DefaultValue "state/forex_mt5_demo_bridge_state.json"),
    "--log-path", (Env-OrDefault -Name "FOREX_BRIDGE_LOG_PATH" -DefaultValue "runtime/forex_mt5_demo_bridge_latest.jsonl"),
    "--session-start-utc", (Env-OrDefault -Name "FOREX_SESSION_START_UTC" -DefaultValue "6"),
    "--session-end-utc", (Env-OrDefault -Name "FOREX_SESSION_END_UTC" -DefaultValue "20"),
    "--max-signal-age-bars", (Env-OrDefault -Name "FOREX_BRIDGE_MAX_SIGNAL_AGE_BARS" -DefaultValue "1"),
    "--max-bars", (Env-OrDefault -Name "FOREX_BRIDGE_MAX_BARS" -DefaultValue "5000"),
    "--max-open-per-pair", (Env-OrDefault -Name "FOREX_BRIDGE_MAX_OPEN_PER_PAIR" -DefaultValue "1"),
    "--mt5-deviation-points", (Env-OrDefault -Name "FOREX_BRIDGE_MT5_DEVIATION_POINTS" -DefaultValue "20"),
    "--mt5-magic", (Env-OrDefault -Name "FOREX_BRIDGE_MT5_MAGIC" -DefaultValue "260308")
)

if ($env:FOREX_BRIDGE_SEND_ORDERS -eq "1") {
    $argsList += "--send-orders"
}

python @argsList
