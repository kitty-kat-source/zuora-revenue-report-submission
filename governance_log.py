"""Append-only governance audit log for Zuora Revenue batch runs (JSONL).

Logs user prompts, batch actions, and all errors. Never writes secrets (URLs, tokens).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GOVERNANCE_ROOT = Path(r"C:\Zuora_Reports\governance")
AUDIT_LOG = GOVERNANCE_ROOT / "audit.jsonl"
ACTIVE_SESSION = GOVERNANCE_ROOT / "active_session.json"
MAX_MESSAGE_LEN = 4000

# Strip presigned query strings if accidentally passed
_URL_SECRET_RE = re.compile(
    r"(https?://[^\s?]+)\?[^\s\"']+", re.IGNORECASE
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sanitize_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value)
    text = _URL_SECRET_RE.sub(r"\1?<redacted>", text)
    if len(text) > MAX_MESSAGE_LEN:
        return text[:MAX_MESSAGE_LEN] + "…[truncated]"
    return text


def _sanitize_obj(obj: Any) -> Any:
    if isinstance(obj, str):
        return _sanitize_text(obj)
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            key = str(k).lower()
            if key in {"url", "presignedurl", "downloadurl", "authorization", "token"}:
                out[k] = "<redacted>"
            else:
                out[k] = _sanitize_obj(v)
        return out
    if isinstance(obj, list):
        return [_sanitize_obj(x) for x in obj]
    return obj


def append_event(
    event: str,
    session_id: str | None = None,
    **fields: Any,
) -> dict:
    GOVERNANCE_ROOT.mkdir(parents=True, exist_ok=True)
    payload = _sanitize_obj({k: v for k, v in fields.items() if v is not None})
    record = {
        "ts": _now(),
        "event": event,
        "sessionId": session_id,
        **payload,
    }
    with AUDIT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def start_session(
    user_prompt: str,
    excel_path: str | None = None,
    period: str | None = None,
    notes: str | None = None,
    sheet_id: str | None = None,
) -> dict:
    session_id = uuid.uuid4().hex
    meta = {
        "sessionId": session_id,
        "startedAt": _now(),
        "userPrompt": _sanitize_text(user_prompt) or "",
        "excelPath": excel_path,
        "period": period,
        "notes": _sanitize_text(notes),
        "sheetId": sheet_id,
    }
    GOVERNANCE_ROOT.mkdir(parents=True, exist_ok=True)
    ACTIVE_SESSION.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    append_event(
        "session_start",
        session_id=session_id,
        userPrompt=meta["userPrompt"],
        excelPath=excel_path,
        period=period,
        notes=notes,
        sheetId=sheet_id,
    )
    return meta


def load_active_session() -> dict | None:
    if not ACTIVE_SESSION.exists():
        return None
    try:
        return json.loads(ACTIVE_SESSION.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def complete_session(session_id: str, summary: dict | None = None) -> dict:
    record = append_event("session_complete", session_id=session_id, summary=summary or {})
    active = load_active_session()
    if active and active.get("sessionId") == session_id:
        ACTIVE_SESSION.unlink(missing_ok=True)
    return record


def log_error(
    session_id: str,
    step: str,
    message: str,
    excel_row: int | None = None,
    report_name: str | None = None,
    layout_name: str | None = None,
    run_id: str | None = None,
    **extra: Any,
) -> dict:
    return append_event(
        "error",
        session_id=session_id,
        step=step,
        message=_sanitize_text(message),
        excelRow=excel_row,
        reportName=report_name,
        layoutName=layout_name,
        runId=run_id,
        **extra,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Zuora batch governance audit log (append-only JSONL)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_start = sub.add_parser("start-session", help="Open a batch session; log user prompt")
    p_start.add_argument("--prompt", required=True, help="Verbatim user request / prompt text")
    p_start.add_argument("--excel", default=None, help="Optional local Excel mirror path")
    p_start.add_argument("--period", default=None, help="e.g. Jul-2026")
    p_start.add_argument("--sheet-id", default=None, help="Google Sheets spreadsheetId")
    p_start.add_argument("--notes", default=None)

    p_event = sub.add_parser("event", help="Append a named event")
    p_event.add_argument("--session-id", required=True)
    p_event.add_argument("--name", required=True, dest="event")
    p_event.add_argument("--data", default="{}", help="JSON object with extra fields")

    p_err = sub.add_parser("error", help="Append an error event")
    p_err.add_argument("--session-id", required=True)
    p_err.add_argument("--step", required=True, help="submit|poll|download|validate|skip|other")
    p_err.add_argument("--message", required=True)
    p_err.add_argument("--row", type=int, default=None, dest="excel_row")
    p_err.add_argument("--report-name", default=None)
    p_err.add_argument("--layout-name", default=None)
    p_err.add_argument("--run-id", default=None)
    p_err.add_argument("--data", default="{}", help="Optional extra JSON fields")

    p_done = sub.add_parser("complete-session", help="Close session with optional summary JSON")
    p_done.add_argument("--session-id", required=True)
    p_done.add_argument("--summary", default="{}", help="JSON summary counts")

    p_show = sub.add_parser("show-active", help="Print active session metadata if any")

    args = parser.parse_args()

    if args.cmd == "start-session":
        meta = start_session(args.prompt, args.excel, args.period, args.notes, args.sheet_id)
        print(json.dumps(meta, indent=2))
        return 0

    if args.cmd == "event":
        try:
            data = json.loads(args.data)
        except json.JSONDecodeError as exc:
            print(f"ERROR: invalid --data JSON: {exc}", file=sys.stderr)
            return 1
        record = append_event(args.event, session_id=args.session_id, **data)
        print(json.dumps(record))
        return 0

    if args.cmd == "error":
        try:
            extra = json.loads(args.data)
        except json.JSONDecodeError as exc:
            print(f"ERROR: invalid --data JSON: {exc}", file=sys.stderr)
            return 1
        record = log_error(
            args.session_id,
            args.step,
            args.message,
            excel_row=args.excel_row,
            report_name=args.report_name,
            layout_name=args.layout_name,
            run_id=args.run_id,
            **extra,
        )
        print(json.dumps(record))
        return 0

    if args.cmd == "complete-session":
        try:
            summary = json.loads(args.summary)
        except json.JSONDecodeError as exc:
            print(f"ERROR: invalid --summary JSON: {exc}", file=sys.stderr)
            return 1
        record = complete_session(args.session_id, summary)
        print(json.dumps(record))
        return 0

    if args.cmd == "show-active":
        print(json.dumps(load_active_session() or {}, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
