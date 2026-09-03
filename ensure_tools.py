"""Ensure duckdb and headroom-ai are installed; persist flags under C:\\Zuora_Reports\\_skill_state.json."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPORTS_ROOT = Path(r"C:\Zuora_Reports")
STATE_PATH = REPORTS_ROOT / "_skill_state.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_state() -> dict:
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_state(state: dict) -> None:
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _pip_install(spec: str) -> None:
    subprocess.check_call([sys.executable, "-m", "pip", "install", spec])


def ensure_duckdb(state: dict, force: bool = False) -> dict:
    entry = state.get("duckdb") or {}
    if entry.get("installed") and not force:
        return state
    try:
        import duckdb  # noqa: F401

        version = getattr(duckdb, "__version__", "unknown")
    except ImportError:
        _pip_install("duckdb")
        import duckdb  # noqa: F401

        version = getattr(duckdb, "__version__", "unknown")
    state["duckdb"] = {
        "installed": True,
        "version": version,
        "verifiedAt": _now(),
        "importOk": True,
    }
    return state


def ensure_headroom(state: dict, force: bool = False) -> dict:
    entry = state.get("headroom") or {}
    if entry.get("installed") and not force:
        return state
    import_ok = False
    cli_ok = False
    version = "unknown"
    try:
        import headroom  # noqa: F401

        import_ok = True
        version = getattr(headroom, "__version__", version)
    except ImportError:
        pass
    if not import_ok:
        try:
            from headroom import compress  # noqa: F401

            import_ok = True
        except ImportError:
            _pip_install("headroom-ai[all]")
            try:
                from headroom import compress  # noqa: F401

                import_ok = True
            except ImportError:
                import_ok = False
    try:
        proc = subprocess.run(
            ["headroom", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode == 0:
            cli_ok = True
            out = (proc.stdout or proc.stderr or "").strip()
            if out:
                version = out.splitlines()[0][:80]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        cli_ok = False
    if not import_ok and not cli_ok:
        raise RuntimeError("headroom-ai install failed: import and CLI both unavailable")
    state["headroom"] = {
        "installed": True,
        "version": version,
        "verifiedAt": _now(),
        "importOk": import_ok,
        "cliOk": cli_ok,
    }
    return state


def ensure_requests(state: dict, force: bool = False) -> dict:
    entry = state.get("requests") or {}
    if entry.get("installed") and not force:
        return state
    try:
        import requests  # noqa: F401

        version = getattr(requests, "__version__", "unknown")
    except ImportError:
        _pip_install("requests")
        import requests  # noqa: F401

        version = getattr(requests, "__version__", "unknown")
    state["requests"] = {
        "installed": True,
        "version": version,
        "verifiedAt": _now(),
        "importOk": True,
    }
    return state


def ensure_nemoguardrails(state: dict, force: bool = False) -> dict:
    entry = state.get("nemoguardrails") or {}
    if entry.get("installed") and not force:
        return state
    try:
        import nemoguardrails  # noqa: F401

        version = getattr(nemoguardrails, "__version__", "unknown")
    except ImportError:
        _pip_install("nemoguardrails")
        import nemoguardrails  # noqa: F401

        version = getattr(nemoguardrails, "__version__", "unknown")
    state["nemoguardrails"] = {
        "installed": True,
        "version": version,
        "verifiedAt": _now(),
        "importOk": True,
    }
    return state


def main() -> int:
    force = "--force" in sys.argv
    state = _load_state()
    state = ensure_duckdb(state, force=force)
    state = ensure_headroom(state, force=force)
    state = ensure_requests(state, force=force)
    state = ensure_nemoguardrails(state, force=force)
    _save_state(state)
    print(json.dumps({"ok": True, "statePath": str(STATE_PATH), "state": state}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
