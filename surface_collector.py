"""Morpheus Surface Collector v1.

task_runner.py verifies expected content and submits attestations.
surface_collector.py only collects public and local surfaces for audit and does
not attest, deploy, or modify production files.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


USER_AGENT = "MorpheusSurfaceCollector/1.0"

URLS = [
    "https://defaultverifier.com/",
    "https://defaultverifier.com/start",
    "https://defaultverifier.com/explorer",
    "https://defaultverifier.com/spec/",
    "https://defaultverifier.com/spec/sar-v0.1/",
    "https://defaultverifier.com/spec/continuity-v0.1/",
    "https://defaultverifier.com/spec/continuity-failure-example-v0.1/",
    "https://defaultverifier.com/spec/sar-v0.1/fixtures/",
]

LOCAL_FILES = [
    "../sar-explorer/README.md",
    "../sar-explorer/index.html",
    "../sar-explorer/start.html",
    "../sar-explorer/explorer.html",
    "../settlement-witness/README.md",
    "../settlement-witness/public-spec/spec/sar-v0.1/index.html",
    "../settlement-witness/public-spec/spec/sar-v0.1/fixtures/index.html",
    "../attest-service/README.md",
    "../continuity-analyzer/README.md",
    "AGENTS.md",
]


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def url_capture_name(url: str, index: int) -> str:
    parsed = urlparse(url)
    path = parsed.path.strip("/").replace("/", "__")
    if not path:
        path = "root"
    return f"{index:02d}-{parsed.netloc}__{path}.html"


def local_capture_path(relative_path: str) -> Path:
    cleaned = relative_path.replace("\\", "/")
    while cleaned.startswith("../"):
        cleaned = cleaned[3:]
    return Path(*cleaned.split("/"))


def fetch_url(url: str, output_path: Path) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    result: dict[str, Any] = {
        "url": url,
        "output": output_path.as_posix(),
        "ok": False,
        "status_code": None,
        "byte_count": 0,
        "content_type": None,
        "final_url": None,
        "error": None,
    }

    try:
        with urlopen(request, timeout=30) as response:
            body = response.read()
            output_path.write_bytes(body)
            result.update(
                {
                    "ok": True,
                    "status_code": response.status,
                    "byte_count": len(body),
                    "content_type": response.headers.get("Content-Type"),
                    "final_url": response.geturl(),
                }
            )
    except HTTPError as error:
        body = error.read()
        if body:
            output_path.write_bytes(body)
        result.update(
            {
                "status_code": error.code,
                "byte_count": len(body),
                "content_type": error.headers.get("Content-Type"),
                "final_url": error.geturl(),
                "error": f"HTTPError: {error}",
            }
        )
    except URLError as error:
        result["error"] = f"URLError: {error.reason}"
    except OSError as error:
        result["error"] = f"OSError: {error}"

    return result


def copy_local_file(repo_root: Path, relative_path: str, local_dir: Path) -> dict[str, Any]:
    source = (repo_root / relative_path).resolve()
    destination = local_dir / local_capture_path(relative_path)
    result: dict[str, Any] = {
        "path": relative_path,
        "source": str(source),
        "output": destination.as_posix(),
        "ok": False,
        "missing": False,
        "byte_count": 0,
        "error": None,
    }

    if not source.is_file():
        result["missing"] = True
        return result

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        result.update({"ok": True, "byte_count": destination.stat().st_size})
    except OSError as error:
        result["error"] = f"OSError: {error}"

    return result


def write_summary_md(summary: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Morpheus Surface Collector v1",
        "",
        f"- Timestamp: {summary['timestamp']}",
        f"- Report directory: {summary['report_dir']}",
        "",
        "## Collected URLs",
        "",
    ]

    for item in summary["urls"]:
        status = "OK" if item["ok"] else "ERROR"
        status_code = item["status_code"] if item["status_code"] is not None else "n/a"
        lines.append(
            f"- {status} `{item['url']}` -> `{item['output']}` "
            f"(status: {status_code}, bytes: {item['byte_count']}, "
            f"type: {item['content_type'] or 'n/a'}, final: {item['final_url'] or 'n/a'})"
        )

    lines.extend(["", "## Collected Local Files", ""])
    for item in summary["local_files"]:
        status = "OK" if item["ok"] else "MISSING" if item["missing"] else "ERROR"
        lines.append(
            f"- {status} `{item['path']}` -> `{item['output']}` "
            f"(bytes: {item['byte_count']})"
        )

    lines.extend(["", "## Errors", ""])
    errors = [
        f"- URL `{item['url']}`: {item['error']}"
        for item in summary["urls"]
        if item["error"]
    ]
    errors.extend(
        f"- Local file `{item['path']}`: {'missing' if item['missing'] else item['error']}"
        for item in summary["local_files"]
        if item["missing"] or item["error"]
    )
    lines.extend(errors or ["- None"])

    lines.extend(
        [
            "",
            "## Next Step",
            "",
            "Give this bundle to an LLM or future Morpheus Surface Auditor for semantic analysis.",
            "",
        ]
    )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def collect(repo_root: Path) -> Path:
    collected_at = timestamp()
    report_dir = repo_root / "reports" / "surface-audits" / collected_at
    urls_dir = report_dir / "urls"
    local_dir = report_dir / "local-files"
    urls_dir.mkdir(parents=True, exist_ok=True)
    local_dir.mkdir(parents=True, exist_ok=True)

    url_results = [
        fetch_url(url, urls_dir / url_capture_name(url, index))
        for index, url in enumerate(URLS, start=1)
    ]
    local_results = [copy_local_file(repo_root, path, local_dir) for path in LOCAL_FILES]

    summary: dict[str, Any] = {
        "collector": "Morpheus Surface Collector v1",
        "timestamp": collected_at,
        "user_agent": USER_AGENT,
        "report_dir": str(report_dir),
        "urls": url_results,
        "local_files": local_results,
        "note": (
            "task_runner.py verifies expected content and submits attestations. "
            "surface_collector.py only collects surfaces for audit and does not attest."
        ),
    }

    (report_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    write_summary_md(summary, report_dir / "summary.md")
    return report_dir


def main() -> int:
    repo_root = Path(__file__).resolve().parent
    report_dir = collect(repo_root)
    print(report_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
