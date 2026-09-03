"""Download Zuora presigned URLs to local paths. Light files only — use one worker for heavy CSVs."""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def download_one(url: str, dest: str, chunk_size: int = 1024 * 1024) -> dict:
    import requests

    path = Path(dest)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    downloaded = 0
    try:
        with requests.get(url, stream=True, timeout=(30, 600)) as resp:
            resp.raise_for_status()
            with tmp.open("wb") as out:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if chunk:
                        out.write(chunk)
                        downloaded += len(chunk)
        tmp.replace(path)
        return {"dest": str(path), "ok": True, "bytes": downloaded}
    except Exception as exc:  # noqa: BLE001
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return {"dest": dest, "ok": False, "error": str(exc), "bytes": downloaded}


def load_jobs(args: argparse.Namespace) -> list[dict]:
    if args.file:
        raw = Path(args.file).read_text(encoding="utf-8")
    elif args.jobs_json:
        raw = args.jobs_json
    else:
        raw = sys.stdin.read()
    jobs = json.loads(raw)
    if not isinstance(jobs, list):
        raise ValueError("jobs must be a JSON array of {url, dest} objects")
    return jobs


def main() -> int:
    parser = argparse.ArgumentParser(description="Parallel presigned URL downloads")
    parser.add_argument("jobs_json", nargs="?", help="JSON array [{url, dest}, ...]")
    parser.add_argument("--file", help="Path to JSON jobs file")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    jobs = load_jobs(args)
    workers = max(1, args.workers)
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(download_one, job["url"], job["dest"]): job for job in jobs
        }
        for fut in as_completed(futures):
            results.append(fut.result())

    ok = all(r.get("ok") for r in results)
    print(json.dumps({"ok": ok, "results": results}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
