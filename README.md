# Zuora Revenue Report Submission

Cursor Agent skill to submit, poll, download, and validate Zuora Revenue reports via MCP — with Google Sheet batch intake, heavy-first queue ordering, DuckDB validation, governance audit log, and NeMo Guardrails.

## Quick start (Windows)

```powershell
git clone https://github.com/kitty-kat-source/zuora-revenue-report-submission.git
cd zuora-revenue-report-submission
.\setup\setup.ps1
```

**Important:** run `setup.ps1` from the **git clone**, not from `%USERPROFILE%\.cursor\skills\zuora-revenue-report-submission\`. Running from the installed skill folder can corrupt files (e.g. `ensure_tools.py` becoming a directory).

Then **only edit credentials** in `%USERPROFILE%\.cursor\mcp.json`:

```json
"zuora-mcp": {
  "auth": {
    "CLIENT_ID": "your-client-id-here",
    "CLIENT_SECRET": "your-client-secret-here"
  }
}
```

Reload Cursor. Enable **Read-Write** for Zuora MCP in OneID Admin Console → AI.

## What setup.ps1 does

| Step | Action |
|------|--------|
| 1 | Copies this repo into `%USERPROFILE%\.cursor\skills\zuora-revenue-report-submission\` |
| 2 | Creates `C:\Zuora_Reports\` + `governance\` + empty `validation_index.json` |
| 3 | Creates `%USERPROFILE%\.mcp-google-sheets\` for Google Sheets MCP |
| 4 | Writes `mcp.json` from `setup/mcp.json.template` (skipped if `mcp.json` already exists unless `-ForceMcp`) |
| 5 | Runs `ensure_tools.py` (duckdb, headroom, requests, openpyxl, nemoguardrails) |

### Setup flags

```powershell
.\setup\setup.ps1 -ForceMcp          # overwrite existing mcp.json from template
.\setup\setup.ps1 -ReportsRoot D:\Zuora_Reports
```

## MCP servers (template)

| Server key in mcp.json | Cursor namespace | Purpose |
|------------------------|------------------|---------|
| `zuora-mcp` | `user-zuora-mcp` | Submit, poll, download URL, summarize |
| `google-sheets-api` | `user-google-sheets-api` | Canonical batch sheet read/write |
| `google-sheets-official` | optional | Alternate Sheets MCP |

**Sandbox URL (default):** `https://sandbox.na.zuora.com/mcp`  
**Production:** `https://na.zuora.com/mcp`

## Canonical Google Sheet

| Field | Value |
|-------|-------|
| Title | Agent-test |
| spreadsheetId | `1V5FVIi8iYkLeae-66_ca0-gNJk6eJ7rFPCWOp1f2gFk` |
| Active tab | `Current` (rows 3–20 = 18 report rows) |

## Usage in Cursor

```
/zuora-revenue-report-submission Run the full Jul-2026 batch from the canonical Google Sheet (Current tab).
```

Use **Cursor Desktop** (local Agent) — not Cloud Agent (needs local `C:\Zuora_Reports\` paths).

## Repo layout

```
zuora-revenue-report-submission/
  SKILL.md                 # Agent instructions (attach or auto-discover)
  ensure_tools.py          # Bootstrap Python deps
  validate_report_duckdb.py
  parallel_download.py
  governance_log.py
  check_guardrails.py
  guardrails/
  setup/
    setup.ps1              # One-command install
    mcp.json.template      # MCP config — edit CLIENT_ID/SECRET after setup
```

## Local paths after runs

```
C:\Zuora_Reports\
  governance\audit.jsonl
  validation_index.json
  Jul-2026\*.csv
```

## Security

- **Never commit** `mcp.json` with real credentials (`.gitignore` blocks it).
- Governance log redacts presigned URLs and tokens automatically.
- Zuora MCP only — no local REST/OAuth clients.

## License

Internal use — Trimble Zuora Revenue reporting workflow.
