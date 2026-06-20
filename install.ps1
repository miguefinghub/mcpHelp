param(
    [switch]$Force,
    [string]$PythonVersion = "3.12"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPath = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
$VscodeDir = Join-Path $ProjectRoot ".vscode"
$McpJsonPath = Join-Path $VscodeDir "mcp.json"
$LocalConfigDir = Join-Path $ProjectRoot ".mcp-local"
$MikrotikEnvPath = Join-Path $LocalConfigDir "mikrotik.env"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "[STEP] $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Read-Required {
    param(
        [string]$Prompt,
        [string]$Default = ""
    )

    while ($true) {
        if ($Default) {
            $Value = Read-Host "$Prompt [$Default]"
            if ([string]::IsNullOrWhiteSpace($Value)) {
                $Value = $Default
            }
        } else {
            $Value = Read-Host $Prompt
        }

        if (-not [string]::IsNullOrWhiteSpace($Value)) {
            return $Value.Trim()
        }
        Write-Warn "Value is required."
    }
}

function Read-RequiredPassword {
    while ($true) {
        $Secure = Read-Host "MikroTik SSH password" -AsSecureString
        $Plain = [System.Net.NetworkCredential]::new("", $Secure).Password
        if (-not [string]::IsNullOrWhiteSpace($Plain)) {
            return $Plain
        }
        Write-Warn "Password is required."
    }
}

function ConvertTo-EnvValue {
    param([string]$Value)
    $Escaped = $Value.Replace("\", "\\").Replace('"', '\"')
    return '"' + $Escaped + '"'
}

function Confirm-Reinstall {
    if ($Force) {
        return $true
    }

    $Existing = @()
    foreach ($Path in @($VenvPath, $McpJsonPath, $LocalConfigDir)) {
        if (Test-Path $Path) {
            $Existing += $Path
        }
    }

    if ($Existing.Count -eq 0) {
        return $true
    }

    Write-Warn "Existing MCP Help configuration was found:"
    foreach ($Path in $Existing) {
        Write-Host "  - $Path"
    }
    Write-Warn "Reinstalling will remove the existing venv and local MCP/MikroTik configuration."

    while ($true) {
        $Answer = Read-Host "Reinstall and reconfigure from zero? Type YES to continue or NO to cancel"
        if ($Answer -eq "YES") {
            return $true
        }
        if ($Answer -eq "NO") {
            return $false
        }
        Write-Warn "Please type YES or NO."
    }
}

function Clear-PreviousInstall {
    foreach ($Path in @($VenvPath, $LocalConfigDir, $McpJsonPath)) {
        if (Test-Path $Path) {
            Remove-Item -LiteralPath $Path -Recurse -Force
            Write-Ok "Removed $Path"
        }
    }
}

function Ensure-Uv {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Write-Ok "uv found"
        return
    }

    Write-Step "uv not found. Installing uv with winget"
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "uv is missing and winget is not available. Install uv from https://docs.astral.sh/uv/ and rerun install.ps1."
    }

    winget install --id Astral.UV -e --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "winget failed to install uv."
    }

    $UserBin = Join-Path $env:USERPROFILE ".local\bin"
    if (Test-Path (Join-Path $UserBin "uv.exe")) {
        $env:PATH = "$UserBin;$env:PATH"
    }

    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "uv was installed but is not available in this PowerShell session. Open a new terminal and rerun install.ps1."
    }

    Write-Ok "uv installed"
}

function Test-RouterPing {
    param([string]$HostName)

    Write-Step "Checking basic router connectivity with ping"
    $PingOk = Test-Connection -ComputerName $HostName -Count 2 -Quiet -ErrorAction SilentlyContinue
    if (-not $PingOk) {
        throw "Ping failed for '$HostName'. Basic network connectivity is not available or ICMP is blocked."
    }
    Write-Ok "Ping succeeded for $HostName"
}

function Write-MikrotikEnv {
    param(
        [string]$HostName,
        [string]$User,
        [string]$Password,
        [int]$Port
    )

    New-Item -ItemType Directory -Path $LocalConfigDir -Force | Out-Null

    $Lines = @(
        "# Local secrets for MCP Help MikroTik. Do not commit this file.",
        "MIKROTIK_HOST=$(ConvertTo-EnvValue $HostName)",
        "MIKROTIK_USER=$(ConvertTo-EnvValue $User)",
        "MIKROTIK_PASSWORD=$(ConvertTo-EnvValue $Password)",
        "MIKROTIK_PORT=$Port"
    )
    Set-Content -Path $MikrotikEnvPath -Value $Lines -Encoding UTF8
    Write-Ok "Wrote local MikroTik config: $MikrotikEnvPath"
}

function Write-McpJson {
    New-Item -ItemType Directory -Path $VscodeDir -Force | Out-Null

    $Config = [ordered]@{
        servers = [ordered]@{
            mikrotik = [ordered]@{
                type = "stdio"
                command = '${workspaceFolder}/.venv/Scripts/python.exe'
                args = @(
                    "-m",
                    "mcp_help.servers.mikrotik.server",
                    "--env-file",
                    '${workspaceFolder}/.mcp-local/mikrotik.env'
                )
                cwd = '${workspaceFolder}'
                env = [ordered]@{
                    PYTHONUNBUFFERED = "1"
                }
            }
        }
    }

    $Json = $Config | ConvertTo-Json -Depth 20
    Set-Content -Path $McpJsonPath -Value $Json -Encoding UTF8
    Write-Ok "Wrote VS Code MCP config: $McpJsonPath"
}

function Read-JsonSettings {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return $null
    }

    $Raw = Get-Content -Raw -Path $Path
    $Raw = [regex]::Replace($Raw, "(?m)//.*$", "")
    $Raw = [regex]::Replace($Raw, "/\*.*?\*/", "", "Singleline")
    $Raw = [regex]::Replace($Raw, ",(\s*[}\]])", '$1')

    try {
        return $Raw | ConvertFrom-Json
    } catch {
        Write-Warn "Could not parse VS Code settings file: $Path"
        return $null
    }
}

function Get-SettingValue {
    param(
        [object]$Settings,
        [string]$Name
    )

    if ($null -eq $Settings) {
        return $null
    }

    $Property = $Settings.PSObject.Properties[$Name]
    if ($null -eq $Property) {
        return $null
    }
    return $Property.Value
}

function Test-VSCodeMcpReadiness {
    Write-Step "Checking VS Code / Copilot MCP readiness"
    Write-Host "VS Code must allow MCP servers and you must trust/enable the 'mikrotik' server from MCP: List Servers."

    $CodeCmd = Get-Command code -ErrorAction SilentlyContinue
    if (-not $CodeCmd) {
        Write-Warn "VS Code CLI 'code' was not found in PATH. Cannot verify extensions from this terminal."
    } else {
        $Version = (& code --version 2>$null | Select-Object -First 1)
        if ($Version) {
            Write-Ok "VS Code CLI found: $Version"
        }

        $Extensions = & code --list-extensions 2>$null
        if ($Extensions -contains "GitHub.copilot") {
            Write-Ok "GitHub Copilot extension is installed"
        } else {
            Write-Warn "GitHub Copilot extension was not found with 'code --list-extensions'."
        }
    }

    $SettingsPaths = @(
        (Join-Path $env:APPDATA "Code\User\settings.json"),
        (Join-Path $env:APPDATA "Code - Insiders\User\settings.json")
    )

    foreach ($SettingsPath in $SettingsPaths) {
        if (-not (Test-Path $SettingsPath)) {
            continue
        }

        $Settings = Read-JsonSettings -Path $SettingsPath
        $Access = Get-SettingValue -Settings $Settings -Name "chat.mcp.access"
        $AutoStart = Get-SettingValue -Settings $Settings -Name "chat.mcp.autoStart"
        $AutoStartLegacy = Get-SettingValue -Settings $Settings -Name "chat.mcp.autostart"

        if ($Access -eq "none") {
            throw "VS Code setting chat.mcp.access is 'none' in $SettingsPath. MCP support is disabled."
        }
        if ($Access) {
            Write-Ok "chat.mcp.access = $Access in $SettingsPath"
        } else {
            Write-Warn "chat.mcp.access is not explicitly set in $SettingsPath. If MCP is blocked by policy, VS Code will show it."
        }

        if ($AutoStart -eq $false -or $AutoStartLegacy -eq $false) {
            Write-Warn "MCP autostart is disabled in $SettingsPath. You can still start the server manually with MCP: List Servers."
        }
    }
}

function Invoke-McpSmokeTest {
    Write-Step "Running MCP stdio smoke test"
    $SmokeCode = @"
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    params = StdioServerParameters(
        command=r"$VenvPython",
        args=["-m", "mcp_help.servers.mikrotik.server", "--env-file", r"$MikrotikEnvPath"],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            tools = await session.list_tools()
            print(f"{init.serverInfo.name}: {len(tools.tools)} tools")

asyncio.run(main())
"@
    $SmokeCode | & $VenvPython -
    if ($LASTEXITCODE -ne 0) {
        throw "MCP stdio smoke test failed."
    }
    Write-Ok "MCP stdio smoke test passed"
}

Write-Step "Checking project files"
foreach ($Required in @("pyproject.toml", "mcp_help\servers\mikrotik\server.py")) {
    if (-not (Test-Path (Join-Path $ProjectRoot $Required))) {
        throw "Missing required file: $Required. Run install.ps1 from the repository root."
    }
}
Write-Ok "Project root: $ProjectRoot"

if (-not (Confirm-Reinstall)) {
    Write-Warn "Installation cancelled. Existing configuration was not changed."
    exit 0
}

Clear-PreviousInstall

Write-Step "Collecting MikroTik connection data"
$RouterHost = Read-Required -Prompt "MikroTik router IP or host" -Default "192.168.88.1"
$RouterUser = Read-Required -Prompt "MikroTik SSH user" -Default "admin"
$RouterPassword = Read-RequiredPassword
$RouterPortRaw = Read-Required -Prompt "MikroTik SSH port" -Default "22"
try {
    $RouterPort = [int]$RouterPortRaw
} catch {
    throw "MikroTik SSH port must be an integer."
}
if ($RouterPort -lt 1 -or $RouterPort -gt 65535) {
    throw "MikroTik SSH port must be between 1 and 65535."
}

Test-RouterPing -HostName $RouterHost

Ensure-Uv

Write-Step "Creating .venv with Python $PythonVersion"
uv venv --python $PythonVersion $VenvPath
if ($LASTEXITCODE -ne 0) {
    throw "uv failed to create the virtual environment with Python $PythonVersion."
}
Write-Ok "Virtual environment ready"

Write-Step "Installing project and dev dependencies"
uv pip install --python $VenvPython -e ".[dev]"
if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed."
}
Write-Ok "Dependencies installed"

Write-Step "Writing local MCP configuration"
Write-MikrotikEnv -HostName $RouterHost -User $RouterUser -Password $RouterPassword -Port $RouterPort
Write-McpJson

Test-VSCodeMcpReadiness

Write-Step "Validating local config parser"
& $VenvPython -m mcp_help.servers.mikrotik.server --env-file $MikrotikEnvPath --validate
if ($LASTEXITCODE -ne 0) {
    throw "MikroTik SSH validation failed."
}
Write-Ok "MikroTik SSH validation passed"

Invoke-McpSmokeTest

Write-Step "Running local contract tests"
& $VenvPython -m pytest
if ($LASTEXITCODE -ne 0) {
    throw "Tests failed."
}
Write-Ok "Tests passed"

Write-Host ""
Write-Host "Ready. Open this folder in VS Code with: code ." -ForegroundColor Green
Write-Host "Then run MCP: List Servers, trust/enable 'mikrotik', and use Copilot Chat in Agent mode." -ForegroundColor Green
