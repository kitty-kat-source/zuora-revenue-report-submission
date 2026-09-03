---
name: zuora-revenue-report-submission
description: Submit, monitor, download, and validate Zuora Revenue reports via user-zuora-mcp. Batch intake and write-back use the canonical Google Sheet (Agent-test) via user-google-sheets-api. Heavy-first ordering, queue-aware MCP polling, DuckDB validation, governance audit log, NeMo Guardrails. MCP only for Zuora — no REST/OAuth clients.
---

# Zuora Revenue Report Submission

Submit and validate Zuora Revenue reports via `user-zuora-mcp` using `manage_revenue_reports` and `summarize_revenue_report`, with local archive + DuckDB count validation for batch runs.

## Mandatory rule: agent guardrails (read first)

### Zuora access — MCP only (non-negotiable)

All Zuora Revenue operations — list, layout, submit, poll, download URL, summarize — MUST use **`user-zuora-mcp`** only.

**Forbidden (never do these):**
- Creating or using a local Zuora REST/OAuth client (`zuora_client.py`, custom API wrappers, etc.)
- Reading `mcp.json` (or any MCP config) to extract `CLIENT_ID`, `CLIENT_SECRET`, or other credentials
- Writing credential files such as `zuora_auth.json` under `C:\Zuora_Reports\` or elsewhere
- Calling Zuora REST endpoints directly for submit, poll, status, or download (bypassing MCP)
- Inventing alternate polling paths (“token-free polling”, background runners, local API daemons) not defined in this skill

**Allowed local scripts (this skill folder only):**

| Script | Allowed use |
|--------|-------------|
| `ensure_tools.py` | Bootstrap duckdb, headroom, requests, openpyxl |
| `governance_log.py` | Append-only audit JSONL |
| `check_guardrails.py` | NeMo Guardrails checks (input/output/action/tool) |
| `validate_report_duckdb.py` | Local CSV `COUNT(*)` only |
| `parallel_download.py` | HTTP GET of **presigned URLs** only — no Zuora auth |

Polling is **queue-aware MCP polling** (`get_revenue_report_run_status` via `manage_revenue_reports`) with shell `Sleep` between wakes — see [Queue-aware polling](#queue-aware-polling-batch-runs--mcp-only). That is the only batch polling mechanism.

### NeMo Guardrails (mandatory checkpoints)

Use **NVIDIA NeMo Guardrails** (`check_guardrails.py` + `guardrails/config/`) as a **local rule engine** for programmatic enforcement of the rules above.

**No external LLM API is required.** You are using Cursor for agent intelligence; these guardrails run entirely on your machine as Python regex + custom actions. There is no `models:` block in the config and no calls to OpenAI, Anthropic, or other providers. NeMo here is only the framework — not a second LLM bill.

**Do not enable** NeMo's `self check input` / `self check output` flows (those need an API key). This skill uses **regex check** + **zuora check \*** actions only.

**When to run (required):**

| Checkpoint | Command | Block behavior |
|------------|---------|----------------|
| **Batch start** (before `start-session`) | `python check_guardrails.py --mode input --text "<verbatim user prompt>" --fail` | Do not start batch; explain block reason |
| **Before Zuora/Google MCP call** | `python check_guardrails.py --mode tool --text "user-zuora-mcp/manage_revenue_reports" --fail` | Do not invoke tool |
| **Before local script** (non-trivial shell) | `python check_guardrails.py --mode action --text "<full planned command>" --fail` | Do not run command |
| **Before end-of-batch summary** (optional spot-check) | `python check_guardrails.py --mode output --text "<draft markdown>"` | Trim/redact; do not leak URLs or CSV |

Pass `--session-id <id>` on any check during an open batch to log blocks to `governance\audit.jsonl` (`step`: `guardrail_<mode>`).

**What the rails block:**

- Credential extraction (`mcp.json`, `CLIENT_SECRET`, OAuth tokens, private keys)
- Direct Zuora REST / `zuora_client.py` / MCP bypass attempts
- Presigned URLs and auth material in chat output
- Non-allowlisted local scripts and MCP namespaces/tools
- Truncating/deleting `audit.jsonl`
- Large CSV/MCP dumps in chat

**Config layout:**

```
guardrails/config/
  config.yml          # regex patterns + rail flow wiring
  actions.py          # Zuora-specific custom actions
  rails/zuora.co      # Colang flows for custom actions
```

**Examples:**

```powershell
python check_guardrails.py --mode input --text "/zuora-revenue-report-submission Run Jul-2026 batch" --fail
python check_guardrails.py --mode tool --text "user-google-sheets-api/get_values" --fail
python check_guardrails.py --mode action --text "python parallel_download.py --file C:\Zuora_Reports\_download_jobs.json" --fail
python check_guardrails.py --mode output --text "**Submitted** — Row 19 | runId: 86806" --session-id <id>
```

If `check_guardrails.py` exits non-zero with `--fail`, **stop** and tell the user which rail blocked the action. Do not bypass guardrails mid-batch.

Bootstrap includes `nemoguardrails` via `ensure_tools.py` (stored in `_skill_state.json`).

### Do not continue without explicit user instruction

- If the user **interrupts**, **asks a question**, or **challenges what you are doing** — **stop immediately**. Do not resume submit, poll, or download in the same turn or silently on the next turn.
- Do **not** auto-continue from conversation summaries, partial prior sessions, or resolved IDs unless the user sends a **new explicit run prompt** (or explicitly says “resume” / “continue”).
- When stopped, answer the user’s question only. Wait for their go-ahead before any Zuora MCP calls.

### Autonomous batch runs (when user says so)

When the user says they are stepping away, run autonomously, or “do not ask questions mid-run”:

- Follow **Steps 0 → 5** in [Batch workflow](#batch-workflow-submit-all--queue-aware-poll--heavy-first-download) exactly — no shortcuts, no extra tooling
- **No mid-run questions** — use skill defaults (timing table, heavy-first order, queue-aware poll)
- **Chat output only:** batch start, each **Submitted**, each **Error**, heavy download start/finish, batch complete, plus the **one** end-of-batch summary table
- **Do not** dump MCP JSON, CSV contents, or per-row validation tables mid-batch

### Fresh batch vs resume

- **Fresh batch:** empty `Parameter ID` / `Status` on intake rows; call `start-session` with verbatim user prompt; do not reuse a prior session’s in-memory state
- **Resume:** only when the user explicitly asks; respect existing `Parameter ID` / `Status` in the **Google Sheet**; do not resubmit rows that already have a runId unless user asks

## Mandatory rule: canonical Google Sheet (batch registry)

**All batch intake and write-back use this Google Sheet** unless the user explicitly names a different spreadsheet for a one-off run.

| Field | Value |
|-------|-------|
| **Title** | Agent-test |
| **spreadsheetId** | `1V5FVIi8iYkLeae-66_ca0-gNJk6eJ7rFPCWOp1f2gFk` |
| **URL** | https://docs.google.com/spreadsheets/d/1V5FVIi8iYkLeae-66_ca0-gNJk6eJ7rFPCWOp1f2gFk/edit |
| **Active tab** | `Current` (live intake + write-back for the next batch) |
| **Header + data range** | `Current!A1:T` (row 1 = headers; row 2 = run meta label; row 3+ = batch rows) |

**MCP server:** `user-google-sheets-api`

| Operation | Tool | Notes |
|-----------|------|-------|
| Read batch rows | `get_values` | `range`: `Current!A1:T100` |
| Phase 1 / Phase 2 write-back | `update_values` or `batch_update_values` | One row or multi-cell per call |
| Archive a finished run | `add_sheet` + `update_values` | Copy full snapshot to a new tab before resetting `Current` |
| Reset intake (fresh batch) | `clear_values` then `update_values` on `Current` | Clear write-back cols or full tab as user requests |

**Do not** use local `RevPro_Report_Details.xlsx` as the source of truth when the skill runs a batch — read and write the Google Sheet. Optional: export/mirror to `C:\Zuora_Reports\RevPro_Report_Details.xlsx` after each write-back if the user wants a local copy.

### Multi-tab run history (same spreadsheet)

Each tab uses the same column layout (row 1 = headers, row 2 = meta label in col A, rows 3–20 = 18 report rows).

| Tab | Purpose |
|-----|---------|
| **`Current`** | Active intake — empty `Parameter ID` / `Status`; meta row describes the upcoming run |
| **`<Period> Completed`** | Finished batch archive (e.g. `Jul-2026 Completed`) |
| **`<Period> Incomplete MMDD`** | Mid-run or aborted snapshot (e.g. `Jul-2026 Incomplete 0819`) |
| **`<Period> Partial`** | Partial test batches (e.g. `May-2026 Partial`) |

**Before starting a fresh batch on `Current`:** if the tab has completed or partial write-back data, archive it first — `add_sheet` with a descriptive name, then `update_values` / `batch_update_values` with the full `A1:T20` snapshot (meta row + all 18 rows). Reset `Current` to clean intake (meta row + empty write-back columns).

Existing archive tabs in this spreadsheet: `Jul-2026 Completed`, `Jul-2026 Incomplete 0819`, `Jul-2026 Incomplete 0829`, `May-2026 Partial`.

### Column map (`Current` and archive tabs)

| Col | Header | Write-back phase |
|-----|--------|------------------|
| A | Report Name | intake |
| B | Layout Name | intake |
| C–G | Filter1…Filter5 | intake |
| H–L | Value1…Value5 | intake |
| M | Parameter ID | **Phase 1** (submit) |
| N | Status | **Phase 2** (terminal) |
| O | Submitted Date | **Phase 1** |
| P | Error Message | **Phase 2** / errors |
| Q | Local Path | **Phase 2** |
| R | DuckDB Count | **Phase 2** |
| S | Zuora Count | **Phase 2** |
| T | Validation | **Phase 2** |

**Sheet row number** for data row index `i` (0-based, first data row = 0): **sheet row = `i + 3`** (row 2 is the meta label).

Example Phase 1 write for sheet row 5 (data row index 2): `update_values` range `Current!M5:O5` → `[[runId, "", submittedAt]]` (leave Status empty).

Example Phase 2 write for sheet row 5: `Current!N5:T5` → `[[status, errorMsg, localPath, duckdbCount, zuoraCount, validation]]`.

Use `value_input_option`: **`RAW`** for intake columns A–L (filters/labels); **`USER_ENTERED`** only for dates in Value columns if needed. Use **`RAW`** for runIds and paths in M–T to avoid Sheets mangling long numbers.

**Chat row labels:** cite **sheet row number** (e.g. “Row 5” = `Current` row 5, not 0-based index).

## Mandatory rule: always validate with summary

Whenever the user asks for **report submission**, **download**, or **both**, you MUST validate record counts after the run reaches `Available` and the file is downloaded.

**Batch runs — dual validation (required after each Available + download):**
1. Save file from Zuora **presigned URL** to `C:\Zuora_Reports\<Month-Year>\`
2. **DuckDB** `COUNT(*)` on the local CSV (authoritative local count)
3. **`summarize_revenue_report`** when useful for Zuora `totalRowsInFile` (skip on validation_index memory hit or when user forces duckdb-only)
4. Compare DuckDB vs Zuora → `MATCH` / `MISMATCH` / `DUCKDB_ONLY`
5. Update **Google Sheet** + `C:\Zuora_Reports\validation_index.json` immediately (background per row)
6. **Do not** print the full batch results table until **all** batch rows are terminal

**Single-report runs:** use the single-run response template (including `totalRowsInFile`).

**Minimum deliverable (count-level validation):**
- DuckDB local count (batch) and/or `totalRowsInFile` (Zuora)
- `dataRowsCount` and `summaryType` when summarize is called
- Run context: `runId`, `reportId`, `layoutId`, `filterParameters`, `fileName`, `localPath`

Do not skip local DuckDB validation because the CSV was already summarized remotely.

## Mandatory rule: governance audit log (persistent)

Every batch or single-report run MUST write an **append-only** audit trail under `C:\Zuora_Reports\governance\`.

**Paths:**
- `C:\Zuora_Reports\governance\audit.jsonl` — all events (never delete/truncate for governance)
- `C:\Zuora_Reports\governance\active_session.json` — current open session metadata (removed on `complete-session`)

**Helper:** `governance_log.py` in this skill folder (sanitizes presigned URLs and tokens before write).

### When to log (required)

| When | Command / event |
|------|-----------------|
| **Batch start** (before submit) | `start-session` with **verbatim user prompt**, `--period`, `--sheet-id` (canonical spreadsheetId) |
| **Each successful submit** | `event` → `submit_ok` (`excelRow`, `reportName`, `layoutName`, `runId`, `reportId`, `layoutId`) |
| **Each skipped row** | `event` → `row_skipped` + reason |
| **Any failure** (submit, poll, download, DuckDB, summarize) | `error` with `--step` + `--message` (+ row/report/runId when known) |
| **Terminal poll status** (non-error) | `event` → `poll_terminal` (`status`, `runId`, …) |
| **Download complete** | `event` → `download_ok` (`localPath`, `bytes` if known) |
| **Validation complete** | `event` → `validate_ok` (`duckdbCount`, `validation`, `zuoraCount`) |
| **Batch end** (all rows terminal) | `complete-session` with summary counts (`available`, `error`, `match`, …) |

Log **immediately** on each event — same timing as Google Sheet write-back. Do not wait until end of batch to log errors.

**Single-report runs:** still call `start-session` (prompt + report context) and log errors + `complete-session` when done.

### Examples

```powershell
# Open session — capture what the user asked
python governance_log.py start-session --prompt "<verbatim user message>" --period "Jul-2026" --sheet-id "1V5FVIi8iYkLeae-66_ca0-gNJk6eJ7rFPCWOp1f2gFk"

# Submit OK (use sessionId from start-session JSON output)
python governance_log.py event --session-id <id> --name submit_ok --data "{\"excelRow\":18,\"reportName\":\"RC Rollforward Report\",\"layoutName\":\"Transaction PDT-COGNOS\",\"runId\":\"86850\",\"reportId\":\"1\",\"layoutId\":\"10016\"}"

# Any error
python governance_log.py error --session-id <id> --step poll --message "ORA-01403: no data found" --row 11 --report-name "Waterfall Report" --layout-name "ZWF21" --run-id "86833"

# Batch finished
python governance_log.py complete-session --session-id <id> --summary "{\"total\":18,\"available\":16,\"error\":2,\"match\":1,\"duckdbOnly\":15}"
```

**Security:** Never log presigned URLs, OAuth tokens, or MCP secrets. The helper redacts URL query strings and common secret field names.

**Google Sheet `Error Message` and governance log are both required on failure** — Sheet for operators, JSONL for audit.

## Host tool bootstrap (DuckDB + Headroom)

Run once at the **start of each batch** (or first download in a session). Persist flags so later months skip re-install checks.

**Paths:**
- `C:\Zuora_Reports\_skill_state.json` — install memory for duckdb + headroom
- Helpers (optional): `ensure_tools.py`, `validate_report_duckdb.py` in this skill folder

### Bootstrap algorithm

```
1. Ensure C:\Zuora_Reports exists
2. Read _skill_state.json (create empty {} if missing)
3. duckdb:
   - If state.duckdb.installed == true → SKIP check
   - Else: python -c "import duckdb"
     - If fail: pip install duckdb → re-import
     - Write state.duckdb = { installed: true, version, verifiedAt, importOk: true }
4. headroom (https://github.com/headroomlabs-ai/headroom):
   - If state.headroom.installed == true → SKIP check
   - Else: try `headroom --version` OR `python -c "from headroom import compress"`
     - If fail: pip install "headroom-ai[all]" (Python 3.10+)
     - Write state.headroom = { installed: true, version, verifiedAt, importOk: true }
5. Save _skill_state.json
```

**Force re-check** only if the user asks to reinstall tools, or an import fails mid-run (clear that tool's `installed` flag and retry once).

### Headroom usage (token reduction)

Package: `headroom-ai`. Prefer the Python library for large MCP JSON (layout, status, summarize) before stuffing into context:

```python
from headroom import compress
# compress large tool payloads; keep chat outputs to counts / MATCH lines only
```

Do **not** dump full CSV contents into chat. Prefer shell/script that returns integers only.

Optional full-session wrap is out of scope for monthly batch; library compress is enough.

### `_skill_state.json` example

```json
{
  "duckdb": {
    "installed": true,
    "version": "1.2.0",
    "verifiedAt": "2026-07-13T21:40:00",
    "importOk": true
  },
  "headroom": {
    "installed": true,
    "version": "0.1.0",
    "verifiedAt": "2026-07-13T21:40:00",
    "importOk": true,
    "cliOk": true
  }
}
```

## Local archive (`C:\Zuora_Reports`)

### Folder layout (best for monthly activity)

```
C:\Zuora_Reports\
  _skill_state.json           # tool install flags (read every run; no month walk)
  validation_index.json       # ALL periods — skill memory (read every run first)
  governance\
    audit.jsonl                 # append-only audit (user prompts + all errors + events)
    active_session.json         # open session metadata (removed on complete-session)
  May-2026\                   # downloaded CSVs for that period only
  Jun-2026\
```

Create `C:\Zuora_Reports` and `C:\Zuora_Reports\<Month-Year>` with `exist_ok=True` before first write.

### Month-Year derivation

**Priority:**
1. Sheet `period_name` column if present (or local Excel override)
2. Period LOV from period-related filters (`periodQuarter`, Bill Created Period, Period, etc.) e.g. `May-26`
3. First normalized period-like `Value{i}`
4. Fallback: month of `Submitted Date` (e.g. `Jul-2026`); note in chat

**Folder name:** `May-26` → **`May-2026`** (`{Mon}-{YYYY}`)

### File naming

`{ReportName}_{LayoutName}_{runId}.{ext}` — sanitize spaces and `/` to `_`. Prefer Zuora `fileName` when available, prefixed with `{runId}_` to avoid collisions.

### Presigned download only (S3)

After status is **`Available`**:
1. `get_revenue_report_download_url` → `data.presignedUrl`
2. Download that URL to `C:\Zuora_Reports\<Month-Year>\` (HTTP GET; no AWS credentials, no uploads)

Presigned URLs expire ~30 minutes — download promptly after Available.

## Central validation memory

**File:** `C:\Zuora_Reports\validation_index.json` (root — do **not** require opening each month folder to find prior results).

```json
{
  "updatedAt": "2026-07-13T22:00:00",
  "entries": [
    {
      "period": "May-2026",
      "reportName": "Billing Report",
      "layoutName": "Billing Report-New Cognos",
      "runId": "86310",
      "localPath": "C:\\Zuora_Reports\\May-2026\\….csv",
      "duckdbCount": 25,
      "zuoraCount": 25,
      "validation": "MATCH",
      "validatedAt": "2026-07-13T22:00:00",
      "fileName": "…"
    }
  ]
}
```

**Lookup after Available (before download):**
1. Load root `validation_index.json`
2. Hit on `runId` (or `period+reportName+layoutName+filterFingerprint`) with `validation` in (`MATCH`, `DUCKDB_ONLY`) and `localPath` still exists → **skip download + DuckDB + summarize**; accumulate row for end table from index
3. Miss → download → DuckDB → summarize (if useful) → append/update index → **Google Sheet** write-back

**Revalidate:** if user asks to revalidate, force download/count and overwrite the index entry.

## DuckDB count validation

After download completes (or use helper `validate_report_duckdb.py`):

```sql
SELECT COUNT(*) AS row_count
FROM read_csv_auto('<local_path>', header=true);
```

| Outcome | Meaning |
|---------|---------|
| `MATCH` | DuckDB count == Zuora `totalRowsInFile` |
| `MISMATCH` | Both present and differ |
| `DUCKDB_ONLY` | Zuora total missing/partial; local count still recorded |
| `SKIPPED_MEMORY` | Reused from `validation_index.json` |

Prefer DuckDB over loading large files into pandas. On DuckDB failure: write `Error Message`, notify chat **immediately**; keep local file if download succeeded.

Write-back columns `Local Path`, `DuckDB Count`, `Zuora Count`, `Validation` live in cols Q–T on the canonical sheet.

## Batch intake — Google Sheet (default) / Excel (override only)

**Default:** read intake from the [canonical Google Sheet](#mandatory-rule-canonical-google-sheet-batch-registry) via `user-google-sheets-api` → `get_values`.

**Trigger when the user:**
- Asks to run/submit/validate a Zuora Revenue **batch** (uses canonical sheet automatically)
- Provides a path to `.xlsx` or `.csv` **only when explicitly overriding** the default sheet
- References report/layout rows with filter columns

### Canonical spreadsheet schema

| Column | Role |
|--------|------|
| `Report Name` | Zuora report display name |
| `Layout Name` | Layout display name within that report |
| `Filter1` … `Filter5` | Filter labels (UI `fieldLabel` from layout) |
| `Value1` … `Value5` | Filter values (paired with Filter1…Filter5) |
| `Time Taken-Mins` | Optional — overrides skill lookup table for first-poll wait |
| `period_name` | Optional — drives `Month-Year` folder |
| `Parameter ID` | Write-back: `runId` immediately after successful submit |
| `Status` | Write-back: terminal run status after poll completes |
| `Submitted Date` | Write-back: submission timestamp immediately after successful submit |
| `Error Message` | Write-back: error text on any failure |
| `Local Path` | Write-back: path under `C:\Zuora_Reports\…` |
| `DuckDB Count` | Write-back: local row count |
| `Zuora Count` | Write-back: `totalRowsInFile` when known |
| `Validation` | Write-back: `MATCH` / `MISMATCH` / `DUCKDB_ONLY` / `SKIPPED_MEMORY` |

Accept column aliases (case-insensitive): `report_name` / `Report Name`, `layout_name` / `Layout Name`.

Auto-add missing write-back columns if absent.

### Filter parsing rule (mandatory)

For each row, for `i` in 1…5:

```
IF Filter{i} is present (non-empty label)
  AND Value{i} is NOT null / empty
    → INCLUDE this filter
ELSE
    → IGNORE (do not submit this filter)
```

**Never** submit a filter with an empty value. If all filters are skipped, submit with `filtersJson: []` (layout defaults may apply).

### Value normalization

| Input type | Example | Zuora value | Operator |
|------------|---------|-------------|----------|
| Excel datetime (period LOV) | `2026-05-26` | **`May-26`** | `=` |
| String with operator prefix | `>= 05/22/2026` | `2026-05-22` | `>=` |
| Plain string | `Std Cost`, `Actuals` | as-is | `=` |

**Period LOV format (confirmed):** `{Mon}-{YY}` — e.g. `May-26`, `Jun-26`, `Apr-26`

Convert Excel datetimes to period LOV:
- `datetime(2026, 5, 26)` → `May-26`
- Use Python: `dt.strftime('%b-%y')` then capitalize month → `May-26`

**Date filters (non-period, e.g. Rc Head Updated Date):**
- `>= 05/22/2026` → operator `>=`, value `2026-05-22`
- Parse `MM/DD/YYYY` to `YYYY-MM-DD` for MCP `filtersJson`

### Incompatible row policy

Skip a row **without modifying any existing cells** when any of these fail before submit:

- `Report Name` or `Layout Name` is empty
- No matching `reportId` or `layoutId` in Zuora (after fresh MCP name lookup)
- A filter label cannot be mapped to `fieldName`
- A required layout filter is missing after null-ignore parsing

Optional chat note: `Row N skipped (incompatible): <reason> — left unchanged.`

Rows that already have a `Parameter ID` may be skipped on re-run unless the user asks to resubmit.

### Progressive write-back (mandatory for batch)

Write to the **Google Sheet** in **two phases** per row via `user-google-sheets-api` (`update_values` / `batch_update_values`). **Write after every phase** — do not batch-write only at the end.

#### Phase 1 — Immediately after successful `run_revenue_report`

| Column | Value |
|--------|-------|
| `Parameter ID` | `data.id` (runId) |
| `Submitted Date` | Local timestamp `YYYY-MM-DD HH:MM:SS` (or Zuora `runDate` if returned) |

Do **not** set `Status` yet.

**Chat (immediate — allowed mid-batch):**
```markdown
**Submitted** — Row <N> | <Report Name> / <Layout Name> | **runId: <id>**
Next status check in ~<Time Taken-Mins> min.
```

#### Phase 2 — After poll reaches terminal status

| Column | Value |
|--------|-------|
| `Status` | `Available`, `Error`, `Terminated`, or `Cancelled` |
| `Error Message` | Empty on success; API/MCP message on failure |

On **`Available`**: immediately start **background** download + DuckDB (+ summarize) validation; update `Local Path`, `DuckDB Count`, `Zuora Count`, `Validation` when done. **Do not** print the full batch table yet.

#### On error at any step (submit, poll, download, DuckDB)

| Column | Value |
|--------|-------|
| `Error Message` | Truncated error (first ~500 chars) |
| `Status` | Terminal status if known; else `Error` |
| `Parameter ID` | Keep if submit succeeded before failure |

**Governance:** Immediately append to `governance\audit.jsonl` via `governance_log.py error` (same message + step + sheet row/runId). Required even when Google Sheet write-back succeeds.

**Chat (immediate):**
```markdown
**Error** — Row <N> | <Report Name> / <Layout Name> | **runId: <id>** (if available)
> <error message>
```

#### File target

- Default: **overwrite the source file** the user provided.
- Fallback: `{original}_results.xlsx` or `.csv` if source is read-only.

### Per-layout poll timing (batch runs)

Do **not** use a fixed 2–3 minute wait. Use historical completion times per `(Report Name, Layout Name)`.

**Lookup priority:**
1. Row's `Time Taken-Mins` column (if populated)
2. Skill lookup table below
3. Fallback: **10 minutes**

#### Timing lookup table

| Report Name | Layout Name | Time Taken-Mins |
|-------------|-------------|-----------------|
| Waterfall Report | ZWF06 | 12.95 |
| Waterfall Report | ZWF09 | 4.36 |
| Waterfall Report | ZWF10 | 30.39 |
| Waterfall Report | ZWF11 | 49.59 |
| Waterfall Report | ZWF12 | 45.36 |
| Waterfall Report | ZWF15 | 4.25 |
| Waterfall Report | ZWF16 | 41.26 |
| Waterfall Report | ZWF17 | 40.86 |
| Waterfall Report | ZWF18 | 41.94 |
| Waterfall Report | ZWF19 | 69.96 |
| Waterfall Report | ZWF20 | 44.13 |
| Waterfall Report | ZWF21 | 48.08 |
| Revenue Contract Detail Report | RC Details / Bookings Report | 5.86 |
| Accounting Report | Accounting Detail -COGNOS | 54.09 |
| RC Rollforward Report | Transaction PDT-COGNOS | 126.8 |
| RC Hold/Release Report | Hold/Release - Cognos | 8.53 |
| Billing Report | Billing Report-New Cognos | 1.36 |
| MJE Details Report | MJE Detail Report - Cognos | 2.01 |

Match layout names case-insensitively; tolerate minor spacing differences (e.g. `Accounting Detail -COGNOS` vs `Accounting Detail - COGNOS`).

### Submit and download ordering (batch runs)

**Sheet row order is intake only — not submit or download order.** After parsing compatible rows, sort by effective `Time Taken-Mins` **descending** before Phase A submit:

1. Row's `Time Taken-Mins` column (if populated)
2. Skill timing lookup table above
3. Fallback: **10 minutes**

**Why:** Zuora processes report runs **sequentially** (one at a time in submit order) in this tenant. Submitting heavy layouts first puts the long pole at the **front of the queue**. Billing/MJE (~1–2 min runtime) are submitted last so they sit at the **back** — they cannot finish until every job ahead of them completes.

**Typical heavy-first submit sequence (Jul-2026 Cognos batch):**

| Priority | Layout | ~Time Taken-Mins |
|----------|--------|------------------|
| 1 | Transaction PDT-COGNOS | 126.8 |
| 2 | ZWF19 | 69.96 |
| 3 | Accounting Detail -COGNOS | 54.09 |
| 4 | ZWF11, ZWF21, ZWF18, ZWF20, ZWF12, ZWF16, ZWF17, ZWF10, ZWF06 | 30–49 |
| 5 | Hold/Release, RC Details, ZWF09, ZWF15 | 4–9 |
| 6 | MJE, Billing | 1–2 |

Sheet row numbers and write-back columns are unchanged — only the MCP `run_revenue_report` call sequence changes. Chat **Submitted** lines should cite the **Google Sheet row number**.

**Download queue when multiple rows are Available:**

| File class | Rule |
|------------|------|
| **Heavy** (Transaction PDT, Accounting Detail, waterfall ZWF layouts; typically **>~500 MB** or **>~30 min** historic time) | **One at a time**, **heaviest first** in the download queue |
| **Light** (Billing, MJE, small RC/Hold) | May use `parallel_download.py` with up to **4 workers** |

For every heavy download: fetch a **fresh** presigned URL immediately before starting; if transfer exceeds ~30 minutes, refresh the URL (~25 min TTL buffer). **Never** run two large Cognos CSV downloads in parallel — Jul-2026 batch saw file locks, incomplete reads, and 403/expired URLs.

When both heavy and light rows are Available in the same poll wake: start the **heaviest pending download first**; queue light files for parallel download only when no heavy transfer is active.

#### Sequential queue assumption (batch runs — default)

Zuora RevPro runs Cognos reports **one at a time** in **submit order** (not in parallel). A row submitted last (e.g. Billing) **does not start** until every row ahead of it in the queue finishes.

**Do not** schedule first polls as `submittedAt + Time Taken-Mins` independently per row. That model assumes each report starts immediately at its own submit time — wrong for a sequential queue. Polling Billing at ~1.4 min after *its* submit will always return `Submitted` while PDT and other heavy jobs are still running.

**Record at batch submit time (mandatory):**
- `batchStartAt` — timestamp of the **first** successful submit in heavy-first order
- `submitSequence` — integer 1…N on each row (1 = heaviest / first submitted, N = last submitted e.g. Billing)

#### Queue-aware polling (batch runs — MCP only)

**Default model: front-of-queue polling.** Only the **active row** (first non-terminal row in `submitSequence` order) gets status polls. Rows behind it in the queue are not polled until all predecessors are terminal.

```
FOLLOW_UP_POLL_SECONDS = 180

Per row track: runId, reportId, submitSequence, timingMins, submittedAt,
               batchStartAt, firstPollDone, lastPoll, terminal

After ALL submits complete:
  active = row with smallest submitSequence where terminal == false

First poll for active row:
  - If submitSequence == 1:
      firstPollDue = batchStartAt + round(timingMins × 60)
  - Else (active row k):
      firstPollDue = predecessor_terminalAt + round(timingMins × 60)
      (predecessor = row with submitSequence == k - 1; use its terminal timestamp)

Poll loop until all terminal:
1. active = front non-terminal row in submitSequence order
2. If no active row → complete
3. dueAt = firstPollDue if not firstPollDone else lastPoll + 180
4. Shell Sleep until dueAt — NO MCP during sleep
5. ONE MCP get_revenue_report_run_status for **active row only**
6. If Available → download (heavy-first rules) → DuckDB validate → Google Sheet Phase 2
7. If Error / Terminated / Cancelled → Google Sheet + Error chat immediately; active advances on next loop
8. If still Submitted / running → mark firstPollDone, lastPoll = now; repeat from step 1
   (active unchanged; follow-up in 180s)
9. When active becomes terminal → next row becomes active; compute its firstPollDue
   from predecessor_terminalAt + its timingMins (not from its own submittedAt alone)
```

**Optional batch wake (token savings):** When multiple rows at the back of the queue are all waiting on the same active job, do not poll them. Never use `min(submittedAt + timingMins)` across all rows as the next wake — that incorrectly wakes for Billing while PDT is still running.

**Cumulative ETA (planning / chat only):** Expected finish order ≈ sum of `Time Taken-Mins` for rows 1…k from `batchStartAt` for queue position k. Use for user ETA estimates, not for parallel per-row poll timers.

**Single-report runs** use historic wait + 180s follow-up for that one row (or 3s×60 if user asks for quick poll).

**Do not** use 60s / 30s follow-up intervals for batch runs. Follow-up interval is always **180 seconds**, and only for the **active** queue row after its first-poll window.

**Error rule:** On submit failure or terminal error status, notify chat and write Google Sheet **immediately** — never wait for the poll window or 180s.

#### Legacy note (do not use for batch)

Independent per-row polling (`submittedAt + Time Taken-Mins` for every row, wake at earliest due) is **deprecated** for batch runs. It only applies if the tenant explicitly confirms parallel report execution.

### Token-efficient batch rules (MCP only)

- **Phase A — Submit all rows first** in **heavy-first order** (see Submit and download ordering); Phase 1 Google Sheet write-back after each; record `submitSequence` + `batchStartAt`; short Submitted chat lines only. Sheet row order is not submit order.
- **Queue-aware poll** — poll **active row only** (front of submit queue); never wake on the lightest row's standalone historic time while heavy jobs are still queued.
- **Batch status** — one MCP status call per wake for the active row (not all due rows in parallel).
- **Parallel download (light only)** — small Available rows from the same wake → one `parallel_download.py` call; heavy rows download sequentially, heaviest first; file bytes never go through MCP/chat.
- **DuckDB via script** — integer/JSON only; never load CSV into chat.
- **Headroom-compress** large MCP JSON; keep chat to counts / MATCH lines.
- **Skip summarize** when `validation_index.json` hit or DuckDB-only is acceptable.
- **One** end-of-batch summary table — no per-row full dumps.
- **Do not** use Cursor `/loop` unless user asks (each loop re-invokes agent).

### Parallel download (presigned URLs)

When one or more rows become `Available` in the same poll cycle:

1. Classify each row **heavy** vs **light** (see Submit and download ordering).
2. **Heavy:** MCP `get_revenue_report_download_url` → download immediately (one at a time; heaviest first). Refresh URL if transfer runs long.
3. **Light:** MCP `get_revenue_report_download_url` per row (parallel tool calls) → build job file → run:

```powershell
python parallel_download.py --file C:\Zuora_Reports\_download_jobs.json
```

`_download_jobs.json` shape: `[{"url":"<presignedUrl>","dest":"C:\\Zuora_Reports\\May-2026\\86310_file.csv"}]`

Default **4 parallel workers** (`--workers 4`) for **light jobs only**. Check `validation_index.json` before downloading — skip URLs for rows already `MATCH`/`DUCKDB_ONLY` with file on disk.

Do **not** parallelize heavy Cognos CSV downloads. Do **not** defer heavy downloads until all light rows finish — start the heaviest Available download as soon as no other heavy transfer is active.

### Background validation vs end-of-batch table

| When | What |
|------|------|
| Each report reaches Available + download done | Validate immediately (DuckDB + Zuora + index + Google Sheet) — **background / per-row** |
| Mid-batch chat | **Submitted** and **Error** only (optional one-liner that validation finished for Row N — no table) |
| **All** batch rows terminal (e.g. all 18) | Print **one** tabular batch summary (required) |

Accumulate results in memory / **Google Sheet** / `validation_index.json` as each row finishes; emit the table only at the end.

### Batch workflow (submit-all + queue-aware poll + heavy-first download)

```
Step 0 — Bootstrap: ensure_tools.py (duckdb, headroom, requests, nemoguardrails)
Step 0b — Guardrails: check_guardrails.py --mode input on verbatim user prompt (--fail)
Step 0g — Governance: governance_log.py start-session (verbatim user prompt, --sheet-id, period)
Step 1 — Read canonical Google Sheet (get_values Current!A1:T100); resolve reportId + layoutId via MCP for every row; preview table; build compatible row list
Step 1b — Sort compatible rows by Time Taken-Mins descending (heavy-first submit order)
Step 2 — Submit ALL compatible rows via MCP in that sorted order (Phase 1 Google Sheet write-back + submitSequence + batchStartAt + governance submit_ok after EACH; cite sheet row #)
Step 3 — Poll loop until all terminal (queue-aware — active row only):
         Sleep until active row's first-poll or 180s follow-up → MCP status for active row only
         → on Available: download → DuckDB validate → Google Sheet Phase 2
         → when active terminal: advance to next submitSequence row; first poll = predecessor terminal + its timingMins
         → governance poll_terminal / download_ok / validate_ok or error on failure
Step 4 — governance_log.py complete-session with summary counts
Step 5 — One end-of-batch summary table
Incompatible rows: skip unchanged; log row_skipped to governance
```

**Do not** process row 1 end-to-end before submitting row 2. Submit all first (heavy-first order) so long-running reports enter Zuora's queue at the front. **Poll** follows queue order: only the active (front) non-terminal row is polled; each row's first wait uses its own `Time Taken-Mins` **after** the previous row in submit order finishes — not from its standalone submit time while jobs ahead are still running.

### Filter label → fieldName mapping

1. Call `get_revenue_report_layout` for each unique `(reportId, layoutId)`.
2. Match intake `Filter{i}` to layout `filters[].fieldLabel` (trim, case-insensitive).
3. Use matched `filters[].fieldName` in `filtersJson`.
4. If multiple filters share the same `fieldName`, prefer **exact `fieldLabel` match**.
5. After submit, verify `filterParameters` in the response matches intent.

### Batch submit payload (per row)

```json
{
  "operation": "run_revenue_report",
  "reportId": "<resolved reportId>",
  "layoutId": "<resolved layoutId>",
  "filtersJson": [
    { "fieldName": "<from layout map>", "operator": "=", "value": "May-26" },
    { "fieldName": "updtDt", "operator": ">=", "value": "2026-05-22" }
  ]
}
```

### Batch chat templates

**Per-row submit (immediate):**
```markdown
**Submitted** — Row 17 | Billing Report / Billing Report-New Cognos | **runId: 86310**
Next status check in ~1.4 min.
```

**Per-row error (immediate):**
```markdown
**Error** — Row 12 | Waterfall Report / ZWF19 | **runId: 86308**
> Report run failed: <message>
```

**End-of-batch summary ONLY (after all rows complete):**
```markdown
## Batch validation summary (<N> reports)

| Row | Report | Layout | runId | Status | DuckDB | Zuora | Validation | Local path |
|-----|--------|--------|-------|--------|--------|-------|------------|------------|
| 1 | Billing Report | Billing Report-New Cognos | 86310 | Available | 25 | 25 | MATCH | C:\Zuora_Reports\May-2026\… |
| … | … | … | … | … | … | … | … | … |

| Metric | Count |
|--------|-------|
| Available / MATCH | n |
| MISMATCH | n |
| Error | n |
| Skipped (incompatible / memory) | n |
```

### Tool dependencies

- **Google Sheets:** `user-google-sheets-api` (canonical batch registry)
- Read local `.xlsx` override: `openpyxl` via pandas
- DuckDB: `pip install duckdb` (remembered in `_skill_state.json`)
- Headroom: `pip install "headroom-ai[all]"` (remembered in `_skill_state.json`)
- Zuora MCP: `user-zuora-mcp` with WRITE for submit

## Mandatory rule: fresh MCP layout ID resolution (every report)

**Never submit using cached, inferred, or sequential layout IDs** (e.g. hardcoded maps, `ZWF06→10123…ZWF21→10139`, or “10123–10286” ranges). Wrong IDs can still return a `runId` but produce **`filterParameters: null`**, blank-name orphan rows in Zuora, and unusable output.

### Required before every submit (batch and single-report)

For **each** `(Report Name, Layout Name)` row — including resubmits:

1. **`list_revenue_reports`** with the intake `Report Name` (or exact/partial name) → `reportId`
2. **`list_revenue_report_layouts`** with `reportId` + **`name` = intake `Layout Name`** (exact match) → `layoutId`
3. **`get_revenue_report_layout`** with `(reportId, layoutId)` → confirm layout exists (not 404) and map filter labels to `fieldName`
4. **Post-submit gate:** if `run_revenue_report` response has **`filterParameters: null`** or **`config: null`**, treat as **failed submit** — do **not** write Phase 1 to Google Sheet, log `error` with step `submit`, and **do not** proceed to poll. Re-resolve layout via MCP (steps 1–3); never retry with the same cached ID.

**Forbidden:** skipping MCP lookup because a reference table, prior batch, `_batch_prep.py` map, or skill “cache hint” already lists an ID. Reference tables are **documentation only** — not submit inputs.

**Batch intake:** resolve IDs for all compatible rows via MCP before Phase A submit. Deduplicate MCP calls by unique `(reportName, layoutName)` but still verify each pair at least once per session.

## Key identifiers

| Concept | How to find it |
|---------|---------------|
| `reportId` | `list_revenue_reports` — numeric ID (e.g. Billing Report = **19**) |
| `layoutId` | `list_revenue_report_layouts` with `reportId` + layout **name** filter — numeric ID (e.g. ZWF19 = **10284**) |
| `runId` | Returned by `run_revenue_report` after successful submission |

## Standard workflow

### Step 1 — Discover report

```json
{ "operation": "list_revenue_reports", "name": "<partial name>", "page": 0, "size": 20 }
```

### Step 2 — List layouts

```json
{ "operation": "list_revenue_report_layouts", "reportId": "<id>" }
```

### Step 3 — Inspect layout (filter fieldNames and LOV options)

```json
{ "operation": "get_revenue_report_layout", "reportId": "<id>", "layoutId": "<id>" }
```

Check `filters[]` for `fieldName`, `fieldLabel`, `required`, and `options` (LOV).

### Step 4 — Submit run

> **Requires WRITE** on the MCP tenant (OneID Admin Console → AI → Permission Level = **Read-Write**). Reconnect MCP after changing permissions.

**Primary payload** — use `filtersJson` (not `filters` or `filterValues`):

```json
{
  "operation": "run_revenue_report",
  "reportId": "<id>",
  "layoutId": "<id>",
  "filtersJson": [
    { "fieldName": "<fieldName from layout>", "value": "<value>" }
  ]
}
```

Optional per filter: `"operator": "="` (default), `LIKE`, `IN`, `BETWEEN`, etc.

On success, capture `data.id` as **submission ID** (`runId`). Confirm `filterParameters` in the response matches what the user requested. **If `filterParameters` is null, abort — do not treat as success** (see mandatory fresh layout ID rule).

For **batch runs**, immediately write `Parameter ID` + `Submitted Date` to the Google Sheet and notify chat (see Progressive write-back).

### Step 5 — Poll status

```json
{
  "operation": "get_revenue_report_run_status",
  "reportId": "<id>",
  "runId": "<runId>"
}
```

Poll until terminal: `Available`, `Error`, `Terminated`, or `Cancelled`.

**Single-report runs:** If the user requests a wait before first poll, honor it; otherwise poll every 3s up to 60 attempts.

**Batch runs:** Submit all compatible rows in **heavy-first order**, then **queue-aware** poll loop (active row only) + heavy-first sequential / light parallel download. First poll for queue position 1 at `batchStartAt + Time Taken-Mins`; for position k>1 at `predecessor terminal + Time Taken-Mins`; follow-up every **180s** on active row only. On any error status, notify chat and write Google Sheet immediately.

Save from response:
- `data.config` — parse JSON string if needed → object for summarize step
- `data.filterParameters`, `data.fileName`, `data.runDate`

For **batch runs**, write `Status` (+ `Error Message` if failed) to the Google Sheet when terminal.

### Step 6 — Get download URL and save locally (batch)

```json
{
  "operation": "get_revenue_report_download_url",
  "reportId": "<id>",
  "runId": "<runId>"
}
```

Use `data.presignedUrl` to download into `C:\Zuora_Reports\<Month-Year>\`. No AWS SDK required.

For single-report ad-hoc runs, pasting the raw URL for the user is still fine; markdown links often break long S3 URLs.

### Step 7 — Summarize and validate (REQUIRED)

**Batch:** DuckDB local count (required) + `summarize_revenue_report` for Zuora `totalRowsInFile` when not a memory hit.

**Tool:** `summarize_revenue_report` on `user-zuora-mcp`

```json
{
  "downloadUrl": "<presignedUrl from step 6>",
  "reportConfig": { "Show Filters": "N", "Enable Totals": "N" }
}
```

Pass the parsed `config` object from step 5. If `config` is a JSON string, parse it first.

**Key response fields:**

| Field | Use |
|-------|-----|
| `totalRowsInFile` | Zuora-side record count for comparison |
| `dataRowsCount` | Rows returned in `dataRows` (max 500) |
| `summaryType` | `full` = entire file; `partial` = use DuckDB as local authority |
| `columns` | Column list |
| `aggregations` | Quick insights when needed |
| `totals` | Use when `Enable Totals` = Y |
| `reportMetadata` | Report name, layout, filters when populated |

If `totalRowsInFile` is missing, mark validation `DUCKDB_ONLY` and still record DuckDB count.

## Response template (single-report runs)

```markdown
## Report run <runId>

| Field | Value |
|-------|-------|
| Submission ID | <runId> |
| Status | <status> |
| Report / Layout | <reportId> / <layoutId> |
| Filters applied | <filterParameters> |
| File | <fileName> |
| Local path | <path if downloaded> |

### Validation summary
| Metric | Value |
|--------|-------|
| **DuckDB count** | **<N>** |
| **totalRowsInFile** | **<N>** |
| Validation | MATCH \| MISMATCH \| DUCKDB_ONLY |
| dataRowsCount | <n> |
| summaryType | full \| partial |
```

## Billing Report reference (reportId 19)

| layoutId | Name |
|----------|------|
| 44 | By Revenue Contract |
| 42 | By Item |
| 45 | By POB |
| 40 | Billing Report (default) |
| 10366 | Billing Report-New Cognos |

**Layout 44 filters:**

| fieldName | fieldLabel | Required |
|-----------|-----------|----------|
| `rcId` | Rc Bill RC ID | No |
| `periodQuarter` | Bill Created Period-Filter | **Yes** (LOV: `Apr-26`, `May-26`, etc.) |

## Cognos layout reference (common batch file)

| Report Name | reportId | Layout Name | layoutId |
|-------------|----------|-------------|----------|
| Billing Report | 19 | Billing Report-New Cognos | 10366 |
| MJE Details Report | 57 | MJE Detail Report - Cognos | 10117 |
| Waterfall Report | 5 | ZWF06–ZWF21 | **resolve each by name** (IDs are not sequential; e.g. ZWF19=10284, ZWF20=10285) |
| Revenue Contract Detail Report | 16 | RC Details / Bookings Report | 10384 |
| RC Hold/Release Report | 15 | Hold/Release - Cognos | 10173 |
| RC Rollforward Report | 1 | Transaction PDT-COGNOS | 10016 |
| Accounting Report | 10 | Accounting Detail -COGNOS | 10012 |

**Do not use this table for submit.** Always resolve `reportId` and `layoutId` via MCP name lookup per the mandatory rule above. This table is documentation only.

## MCP tools

| Server | Tool | Purpose |
|--------|------|---------|
| `user-zuora-mcp` | `manage_revenue_reports` | list, layout, submit, status, download URL |
| `user-zuora-mcp` | `summarize_revenue_report` | Zuora-side record count + aggregations |
| `user-google-sheets-api` | `get_values` | Read canonical batch sheet |
| `user-google-sheets-api` | `update_values` / `batch_update_values` | Phase 1 / Phase 2 write-back |
| `user-google-sheets-api` | `clear_values` | Reset sheet for fresh batch |

**Canonical sheet spreadsheetId:** `1V5FVIi8iYkLeae-66_ca0-gNJk6eJ7rFPCWOp1f2gFk`

**Local helpers (this skill folder):**
| Script | Purpose |
|--------|---------|
| `ensure_tools.py` | Check/install duckdb + headroom + requests; update `_skill_state.json` |
| `validate_report_duckdb.py` | `COUNT(*)` on a local CSV path; print integer only |
| `parallel_download.py` | Parallel HTTP GET for presigned URLs — **light files only** (no Zuora auth) |
| `governance_log.py` | Append-only audit JSONL — user prompt, events, all errors (sanitized) |
| `check_guardrails.py` | NeMo Guardrails CLI — input/output/action/tool checks |

## Permission requirements

| Operation | Permission |
|-----------|------------|
| list, layout, status, download, summarize | READ |
| `run_revenue_report` | **WRITE** (OneID → AI → Read-Write) |

If WRITE denied: enable Read-Write in OneID, reconnect MCP, or submit via UI and use read ops + summarize with the returned `runId`.
