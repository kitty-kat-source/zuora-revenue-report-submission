# Zuora Revenue Report Submission — one-time Cursor setup (Windows)
# After running: edit %USERPROFILE%\.cursor\mcp.json and set Zuora CLIENT_ID + CLIENT_SECRET only.

param(
    [switch]$ForceMcp,
    [string]$ReportsRoot = "C:\Zuora_Reports"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$SkillName = "zuora-revenue-report-submission"
$CursorDir = Join-Path $env:USERPROFILE ".cursor"
$SkillsDir = Join-Path $CursorDir "skills"
$SkillDest = Join-Path $SkillsDir $SkillName
$McpTarget = Join-Path $CursorDir "mcp.json"
$McpTemplate = Join-Path $PSScriptRoot "mcp.json.template"
$GSheetsConfig = Join-Path $env:USERPROFILE ".mcp-google-sheets"

Write-Host "=== Zuora Revenue Report Submission — Setup ===" -ForegroundColor Cyan

# 1. Install skill into Cursor skills folder
Write-Host "`n[1/5] Installing skill to $SkillDest ..."
New-Item -ItemType Directory -Force -Path $SkillsDir | Out-Null
if (Test-Path $SkillDest) { Remove-Item -Recurse -Force $SkillDest }
New-Item -ItemType Directory -Force -Path $SkillDest | Out-Null
Get-ChildItem -Path $RepoRoot -Exclude ".git" | Copy-Item -Destination $SkillDest -Recurse -Force
Write-Host "  OK — skill installed."

# 2. Local reports + governance folders
Write-Host "`n[2/5] Creating reports root: $ReportsRoot ..."
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
Write-Host "  OK — folders ready."

# 3. Google Sheets MCP config dir (for mcp-google-sheets-full)
Write-Host "`n[3/5] Google Sheets MCP config dir: $GSheetsConfig ..."
New-Item -ItemType Directory -Force -Path $GSheetsConfig | Out-Null
Write-Host "  OK — create OAuth credentials in Cursor when prompted (first Sheets MCP use)."

# 4. Deploy MCP config from template
Write-Host "`n[4/5] MCP config -> $McpTarget ..."
if ((Test-Path $McpTarget) -and -not $ForceMcp) {
    Write-Host "  SKIP — mcp.json already exists. Use -ForceMcp to overwrite from template." -ForegroundColor Yellow
} else {
    $raw = Get-Content -Raw -Path $McpTemplate
    $homeEsc = $env:USERPROFILE -replace '\\', '\\'
    $raw = $raw -replace 'REPLACE_WITH_YOUR_HOME\\\\.mcp-google-sheets', ($homeEsc + '\\.mcp-google-sheets')
    Set-Content -Path $McpTarget -Value $raw -Encoding utf8
    Write-Host "  OK — template written."
    Write-Host "`n  >>> REQUIRED: Open $McpTarget" -ForegroundColor Yellow
    Write-Host "      Set zuora-mcp auth CLIENT_ID and CLIENT_SECRET (replace REPLACE_WITH_* placeholders)." -ForegroundColor Yellow
    Write-Host "      Production URL (if not sandbox): https://na.zuora.com/mcp" -ForegroundColor DarkGray
}

# 5. Python tooling (duckdb, headroom, nemoguardrails, requests, openpyxl)
Write-Host "`n[5/5] Bootstrapping Python tools ..."
python (Join-Path $SkillDest "ensure_tools.py")
if ($LASTEXITCODE -ne 0) { throw "ensure_tools.py failed" }

Write-Host "`n=== Setup complete ===" -ForegroundColor Green
Write-Host @"

Next steps:
  1. Edit:  $McpTarget
     Replace REPLACE_WITH_YOUR_ZUORA_CLIENT_ID and REPLACE_WITH_YOUR_ZUORA_CLIENT_SECRET
  2. Zuora OneID: AI permission = Read-Write (required for report submit)
  3. Reload Cursor (or restart) so MCP servers reconnect
  4. In Agent chat: /zuora-revenue-report-submission Run Jul-2026 batch from Google Sheet

Skill path: $SkillDest
Reports:    $ReportsRoot
"@
