"""Custom NeMo Guardrails actions for Zuora Revenue batch skill."""

from __future__ import annotations

import re
from typing import Any, Optional

from nemoguardrails.actions import action
from nemoguardrails.actions.rail_outcome import RailOutcome

# Allowed local helpers — must match SKILL.md allowlist
_ALLOWED_LOCAL_SCRIPTS = {
    "ensure_tools.py",
    "governance_log.py",
    "validate_report_duckdb.py",
    "parallel_download.py",
    "check_guardrails.py",
}

# Zuora MCP tool surface
_ALLOWED_MCP = {
    "user-zuora-mcp": {"manage_revenue_reports", "summarize_revenue_report"},
    "user-google-sheets-api": {
        "get_values",
        "update_values",
        "update_formulas",
        "insert_dimension",
        "get_spreadsheet",
        "update_spreadsheet",
        "batch_update_values",
        "clear_values",
        "add_sheet",
    },
}

_FORBIDDEN_INPUT_PHRASES = [
    "resume without asking",
    "auto continue from summary",
    "use cached layout id",
    "hardcoded layout",
    "skip mcp layout lookup",
    "poll every row independently",
    "parallel heavy download",
    "dump full csv",
    "dump mcp json",
]

_FORBIDDEN_ACTION_PHRASES = [
    "zuora_client.py",
    "mcp.json",
    "zuora_auth.json",
    "requests.post(",
    "oauth/token",
    "/v1/revenue",
    "curl.*zuora",
    "pip install zuora",
    "truncate audit.jsonl",
    "delete audit.jsonl",
]

_CANONICAL_SHEET_ID = "1V5FVIi8iYkLeae-66_ca0-gNJk6eJ7rFPCWOp1f2gFk"


def _block(reason: str, **metadata: Any) -> RailOutcome:
    meta = {"reason": reason, **metadata}
    return RailOutcome.block(metadata=meta)


def _allow(**metadata: Any) -> RailOutcome:
    return RailOutcome.allow(metadata=metadata or None)


def _latest_user_message(context: Optional[dict]) -> str:
    if not context:
        return ""
    return str(context.get("user_message") or "")


def _latest_bot_message(context: Optional[dict]) -> str:
    if not context:
        return ""
    return str(context.get("bot_message") or "")


def _contains_any(text: str, phrases: list[str]) -> Optional[str]:
    lower = text.lower()
    for phrase in phrases:
        if phrase.lower() in lower:
            return phrase
    return None


def _regex_any(text: str, patterns: list[str]) -> Optional[str]:
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE | re.DOTALL):
            return pattern
    return None


@action(is_system_action=True)
async def zuora_check_user_intent(context: Optional[dict] = None, **kwargs: Any) -> RailOutcome:
    """Block user prompts that violate Zuora MCP-only and batch governance rules."""
    text = _latest_user_message(context)
    if not text.strip():
        return _allow()

    hit = _contains_any(text, _FORBIDDEN_INPUT_PHRASES)
    if hit:
        return _block(f"Forbidden batch instruction: {hit}")

    if _regex_any(
        text,
        [
            r"(?i)\b(resume|continue)\b.*\b(batch|poll|submit)\b",
            r"(?i)\bwithout\b.*\b(confirm|ask|permission)\b",
        ],
    ):
        # Allow explicit resume phrases
        if not re.search(r"(?i)\b(explicitly\s+)?(resume|continue)\b", text):
            return _block("Implicit auto-resume without explicit user instruction")

    return _allow()


@action(is_system_action=True)
async def zuora_check_agent_output(context: Optional[dict] = None, **kwargs: Any) -> RailOutcome:
    """Block agent chat output that leaks secrets or violates mid-batch verbosity rules."""
    text = _latest_bot_message(context)
    if not text.strip():
        return _allow()

    if len(text) > 12000:
        return _block("Agent output exceeds safe chat size (possible MCP/CSV dump)")

    if _regex_any(
        text,
        [
            r"(?i)\b\d{1,3}(,\d{3})+\s+rows\b.*\b(data|preview|sample)\b",
            r"(?i)(here is the (full )?csv|csv contents|first \d+ lines)",
        ],
    ):
        return _block("Full CSV or large data dump in chat")

    # Mid-batch table before all rows terminal
    if re.search(r"(?i)##\s+batch validation summary", text):
        if re.search(r"(?i)(in progress|polling|submitted — row)", text):
            return _block("End-of-batch summary emitted before all rows terminal")

    return _allow()


@action(is_system_action=True)
async def zuora_check_planned_action(context: Optional[dict] = None, **kwargs: Any) -> RailOutcome:
    """Validate planned shell/MCP action descriptions before execution."""
    text = _latest_user_message(context) or _latest_bot_message(context)
    if not text.strip():
        return _allow()

    hit = _contains_any(text, _FORBIDDEN_ACTION_PHRASES)
    if hit:
        return _block(f"Forbidden planned action: {hit}")

    # Block non-allowlisted python scripts in Zuora context
    py_match = re.search(r"(?i)python\s+([\w/\\.-]+\.py)", text)
    if py_match:
        script = py_match.group(1).replace("\\", "/").split("/")[-1]
        if script not in _ALLOWED_LOCAL_SCRIPTS:
            return _block(f"Non-allowlisted local script: {script}")

    # Encourage canonical sheet when writing batch rows
    if re.search(r"(?i)(update_values|batch_update_values|get_values)", text):
        if "spreadsheet" in text.lower() or "sheet" in text.lower():
            if _CANONICAL_SHEET_ID not in text and "1V5FVIi8iYkLeae" not in text:
                if re.search(r"(?i)(current!|batch|write-back|parameter id)", text):
                    return _block("Batch sheet write without canonical spreadsheetId")

    return _allow()


@action(is_system_action=True)
async def zuora_validate_mcp_tool(
    tool_namespace: str,
    tool_name: str,
    **kwargs: Any,
) -> RailOutcome:
    """Optional programmatic check for MCP tool allowlist (CLI --tool mode)."""
    allowed = _ALLOWED_MCP.get(tool_namespace)
    if allowed is None:
        return _block(f"Unknown MCP namespace: {tool_namespace}")
    if tool_name not in allowed:
        return _block(f"MCP tool not allowlisted: {tool_namespace}/{tool_name}")
    return _allow(namespace=tool_namespace, tool=tool_name)
