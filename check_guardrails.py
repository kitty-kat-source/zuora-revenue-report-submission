"""NeMo Guardrails CLI for Zuora Revenue Report Submission skill.

Runs deterministic regex + custom action rails (no LLM API key required).
Logs blocks to governance audit when --session-id is provided.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(__file__).resolve().parent / "guardrails" / "config"
ACTIONS_PATH = CONFIG_DIR / "actions.py"
GOVERNANCE_LOG = Path(__file__).resolve().parent / "governance_log.py"


def _load_rails():
    from nemoguardrails import LLMRails, RailsConfig
    from nemoguardrails.rails.llm.options import RailType

    rails = LLMRails(RailsConfig.from_path(str(CONFIG_DIR)))
    return rails, RailType


def _load_validate_mcp_tool():
    spec = importlib.util.spec_from_file_location("zuora_guardrail_actions", ACTIONS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load actions from {ACTIONS_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.zuora_validate_mcp_tool


def check_text(
    text: str,
    *,
    mode: str = "input",
    session_id: str | None = None,
) -> dict[str, Any]:
    if mode == "tool":
        import asyncio

        parts = text.split("/", 1)
        if len(parts) != 2:
            result = {
                "allowed": False,
                "status": "BLOCKED",
                "rail": "zuora_validate_mcp_tool",
                "reason": "tool mode expects namespace/toolName",
                "mode": mode,
            }
            if session_id:
                _log_block(session_id, mode, result["reason"], text)
            return result

        namespace, tool_name = parts[0].strip(), parts[1].strip()
        validate = _load_validate_mcp_tool()
        outcome = asyncio.get_event_loop().run_until_complete(
            validate(namespace, tool_name)
        )
        blocked = outcome.is_blocked
        reason = (outcome.metadata or {}).get("reason") if blocked else None
        result = {
            "allowed": not blocked,
            "status": "BLOCKED" if blocked else "PASSED",
            "rail": "zuora_validate_mcp_tool" if blocked else None,
            "reason": reason,
            "mode": mode,
        }
        if blocked and session_id:
            _log_block(session_id, mode, reason or "MCP tool blocked", text)
        return result

    rails, RailType = _load_rails()

    if mode == "input":
        messages = [{"role": "user", "content": text}]
        rail_types = [RailType.INPUT]
    elif mode == "output":
        messages = [{"role": "assistant", "content": text}]
        rail_types = [RailType.OUTPUT]
    elif mode == "action":
        messages = [{"role": "user", "content": text}]
        rail_types = [RailType.INPUT]
    else:
        raise ValueError(f"Unknown mode: {mode}")

    result_obj = rails.check(messages, rail_types=rail_types)
    status = getattr(result_obj.status, "value", str(result_obj.status))
    blocked = status == "blocked" or status == "BLOCKED"
    payload = {
        "allowed": not blocked,
        "status": status.upper() if isinstance(status, str) else str(result_obj.status),
        "rail": result_obj.rail,
        "content": result_obj.content,
        "mode": mode,
    }
    if blocked and session_id:
        _log_block(session_id, mode, result_obj.rail or "guardrail", text)
    return payload


def _log_block(session_id: str, step: str, message: str, text: str) -> None:
    if not GOVERNANCE_LOG.exists():
        return
    snippet = text[:500].replace('"', "'")
    cmd = [
        sys.executable,
        str(GOVERNANCE_LOG),
        "error",
        "--session-id",
        session_id,
        "--step",
        f"guardrail_{step}",
        "--message",
        f"{message}: {snippet}",
    ]
    try:
        subprocess.run(cmd, check=False, capture_output=True, text=True)
    except OSError:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run NeMo Guardrails for Zuora Revenue batch skill (no LLM required)"
    )
    parser.add_argument("--text", required=True, help="Text to check (prompt, output, or action)")
    parser.add_argument(
        "--mode",
        choices=["input", "output", "action", "tool"],
        default="input",
        help="input=user prompt; output=agent chat; action=planned shell/MCP; tool=namespace/toolName",
    )
    parser.add_argument("--session-id", default=None, help="Log blocks to governance audit")
    parser.add_argument("--fail", action="store_true", help="Exit 1 when blocked")
    args = parser.parse_args()

    try:
        result = check_text(args.text, mode=args.mode, session_id=args.session_id)
    except Exception as exc:
        print(json.dumps({"allowed": False, "status": "ERROR", "error": str(exc)}))
        return 1

    print(json.dumps(result, indent=2))
    if args.fail and not result.get("allowed", True):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
