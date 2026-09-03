# Zuora Revenue Report Submission - one-time Cursor setup (Windows)
# Run from the cloned repo (NOT from %USERPROFILE%\.cursor\skills\...).
# After running: edit %USERPROFILE%\.cursor\mcp.json and set Zuora CLIENT_ID + CLIENT_SECRET only.

param(
    [switch]$ForceMcp,
    [string]$ReportsRoot = "C:\Zuora_Reports"
)

$ErrorActionPreference = "Stop"

function Get-NormalizedPath([string]$Path) {
    if (-not $Path) { return $null }
    return [System.IO.Path]::GetFullPath($Path).TrimEnd([char[]]@('\', '/'))
}

$RepoRoot = Get-NormalizedPath (Join-Path $PSScriptRoot "..")
$SkillName = "zuora-revenue-report-submission"
$CursorDir = Join-Path $env:USERPROFILE ".cursor"
$SkillsDir = Join-Path $CursorDir "skills"
$SkillDest = Get-NormalizedPath (Join-Path $SkillsDir $SkillName)
$McpTarget = Join-Path $CursorDir "mcp.json"
$McpTemplate = Join-Path $PSScriptRoot "mcp.json.template"
$GSheetsConfig = Join-Path $env:USERPROFILE ".mcp-google-sheets"
$SameLocation = ($RepoRoot -eq $SkillDest)

Write-Host "=== Zuora Revenue Report Submission - Setup ===" -ForegroundColor Cyan
Write-Host "Source:  $RepoRoot"
Write-Host "Install: $SkillDest"

# 1. Install skill into Cursor skills folder
Write-Host ""
Write-Host "[1/5] Installing skill to $SkillDest ..."
if ($SameLocation) {
    Write-Host "  SKIP copy - you are running from the installed skill folder." -ForegroundColor Yellow
    Write-Host "  Clone the repo elsewhere and run setup from that clone to refresh files." -ForegroundColor Yellow
} else {
    $SourceEnsureTools = Join-Path $RepoRoot "ensure_tools.py"
    if (-not (Test-Path -LiteralPath $SourceEnsureTools -PathType Leaf)) {
        throw "Source repo is missing ensure_tools.py at $SourceEnsureTools. Run setup from the git clone root."
    }

    New-Item -ItemType Directory -Force -Path $SkillsDir | Out-Null
    if (Test-Path -LiteralPath $SkillDest) {
        Remove-Item -LiteralPath $SkillDest -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $SkillDest | Out-Null

    $null = robocopy $RepoRoot $SkillDest /E /XD .git __pycache__ /XF *.pyc /NFL /NDL /NJH /NJS /NC /NS
    if ($LASTEXITCODE -ge 8) {
        throw "File copy failed (robocopy exit $LASTEXITCODE)."
    }
    Write-Host "  OK - skill installed."
}

# Repair common corruption: ensure_tools.py accidentally created as a folder
$EnsureTools = Join-Path $SkillDest "ensure_tools.py"
if (Test-Path -LiteralPath $EnsureTools -PathType Container) {
    Write-Host "  Repairing ensure_tools.py (was a directory)..." -ForegroundColor Yellow
    $nested = Join-Path $EnsureTools "ensure_tools.py"
    if (Test-Path -LiteralPath $nested -PathType Leaf) {
        Remove-Item -LiteralPath $EnsureTools -Recurse -Force
        Move-Item -LiteralPath $nested -Destination $EnsureTools
    } elseif (-not $SameLocation) {
        Remove-Item -LiteralPath $EnsureTools -Recurse -Force
        Copy-Item -LiteralPath (Join-Path $RepoRoot "ensure_tools.py") -Destination $EnsureTools -Force
    } else {
        throw "ensure_tools.py is a directory at $EnsureTools. Re-clone the repo and run setup from the clone."
    }
}

if (-not (Test-Path -LiteralPath $EnsureTools -PathType Leaf)) {
    throw "ensure_tools.py not found as a file at: $EnsureTools. Run setup from the git clone (not from the skills folder)."
}

# 2. Local reports + governance folders
Write-Host ""
Write-Host "[2/5] Creating reports root: $ReportsRoot ..."
@(
    $ReportsRoot,
    (Join-Path $ReportsRoot "governance")
) | ForEach-Object {
    New-Item -ItemType Directory -Force -Path $_ | Out-Null
}
if (-not (Test-Path (Join-Path $ReportsRoot "validation_index.json"))) {
    @{ updatedAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"); entries = @() } |
        ConvertTo-Json -Depth 5 |
        Set-Content -Path (Join-Path $ReportsRoot "validation_index.json") -Encoding utf8
}
Write-Host "  OK - folders ready."

# 3. Google Sheets MCP config dir (for mcp-google-sheets-full)
Write-Host ""
Write-Host "[3/5] Google Sheets MCP config dir: $GSheetsConfig ..."
New-Item -ItemType Directory -Force -Path $GSheetsConfig | Out-Null
Write-Host "  OK - create OAuth credentials in Cursor when prompted (first Sheets MCP use)."

# 4. Deploy MCP config from template
Write-Host ""
Write-Host "[4/5] MCP config -> $McpTarget ..."
if ((Test-Path $McpTarget) -and -not $ForceMcp) {
    Write-Host "  SKIP - mcp.json already exists. Use -ForceMcp to overwrite from template." -ForegroundColor Yellow
} else {
    $raw = Get-Content -Raw -Path $McpTemplate
    $homeEsc = $env:USERPROFILE -replace '\\', '\\'
    $raw = $raw -replace 'REPLACE_WITH_YOUR_HOME\\\\.mcp-google-sheets', ($homeEsc + '\\.mcp-google-sheets')
    Set-Content -Path $McpTarget -Value $raw -Encoding utf8
    Write-Host "  OK - template written."
    Write-Host "  REQUIRED: Open $McpTarget and set Zuora CLIENT_ID and CLIENT_SECRET." -ForegroundColor Yellow
}

# 5. Python tooling (duckdb, headroom, nemoguardrails, requests)
Write-Host ""
Write-Host "[5/5] Bootstrapping Python tools ..."
& python $EnsureTools
if ($LASTEXITCODE -ne 0) { throw "ensure_tools.py failed (exit $LASTEXITCODE)" }

Write-Host ""
Write-Host "=== Setup complete ===" -ForegroundColor Green
Write-Host "Next steps:"
Write-Host "  1. Edit $McpTarget - set Zuora CLIENT_ID and CLIENT_SECRET"
Write-Host "  2. Zuora OneID: AI permission = Read-Write"
Write-Host "  3. Reload Cursor so MCP servers reconnect"
Write-Host "  4. In Agent chat, run the zuora-revenue-report-submission skill"
Write-Host "Skill path: $SkillDest"
Write-Host "Reports:    $ReportsRoot"
