"""Count rows in a local report CSV via DuckDB. Prints row_count only (token-friendly)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPORTS_ROOT = Path(r"C:\Zuora_Reports")
INDEX_PATH = REPORTS_ROOT / "validation_index.json"


def count_csv(path: Path) -> int:
    import duckdb

    # Escape single quotes for SQL literal
    lit = str(path).replace("'", "''")
    row = duckdb.sql(
        f"SELECT COUNT(*) AS row_count FROM read_csv_auto('{lit}', header=true)"
    ).fetchone()
    return int(row[0]) if row else 0


def upsert_index(entry: dict) -> None:
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    data = {"updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "entries": []}
    if INDEX_PATH.exists():
        try:
            data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    entries = data.get("entries") or []
    run_id = entry.get("runId")
    replaced = False
    for i, existing in enumerate(entries):
        if run_id and existing.get("runId") == run_id:
            entries[i] = {**existing, **entry}
            replaced = True
            break
    if not replaced:
        entries.append(entry)
    data["entries"] = entries
    data["updatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    INDEX_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="DuckDB row count for a Zuora report CSV")
    parser.add_argument("path", help="Local CSV/TSV path")
    parser.add_argument("--zuora-count", type=int, default=None, help="Zuora totalRowsInFile if known")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--period", default=None, help="e.g. May-2026")
    parser.add_argument("--report-name", default=None)
    parser.add_argument("--layout-name", default=None)
    parser.add_argument("--update-index", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of bare integer")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 1

    duckdb_count = count_csv(path)
    zuora = args.zuora_count
    if zuora is None:
        validation = "DUCKDB_ONLY"
    elif zuora == duckdb_count:
        validation = "MATCH"
    else:
        validation = "MISMATCH"

    result = {
        "localPath": str(path),
        "duckdbCount": duckdb_count,
        "zuoraCount": zuora,
        "validation": validation,
    }
    if args.update_index:
        entry = {
            **result,
            "period": args.period,
            "reportName": args.report_name,
            "layoutName": args.layout_name,
            "runId": args.run_id,
            "fileName": path.name,
            "validatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        upsert_index(entry)

    if args.json:
        print(json.dumps(result))
    else:
        print(duckdb_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
