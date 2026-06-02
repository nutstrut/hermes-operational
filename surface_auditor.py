"""Morpheus Surface Auditor v1.

Analyzes the newest bundle created by surface_collector.py and writes a product
strategy audit report. This script is read-only except for creating
surface_audit_report.md in the selected audit bundle.
"""

from __future__ import annotations

import html
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CANONICAL_STATE = "Default Settlement is machine trust infrastructure for autonomous systems."
EVIDENCE_LOOP = [
    "Agent Activation",
    "SAR Receipt",
    "Continuity Receipt",
    "Chained Evidence",
    "Explorer Agent Profile",
    "Badge Verification",
    "Public Trust Report",
]

CURRENT_ACCURACY = {
    "activation": ["activation", "activate", "agent activation"],
    "agent profiles": ["agent profile", "agent detail", "profile"],
    "chained receipts": ["chained receipt", "chained evidence", "chain_id", "evidence chain", "completed chain"],
    "continuity evidence": ["continuity receipt", "continuity evidence", "continuity evaluation", "continuity"],
}

ONBOARDING = {
    "obvious next action": ["start", "verify", "activate", "try", "submit", "copy", "curl", "post "],
    "integration path": ["api", "endpoint", "sdk", "cli", "github", "fixture", "example", "integration"],
    "examples": ["example", "fixture", "sample", "demo", "curl", "json"],
}

NAVIGATION = {
    "Home": ["href=\"/\"", "href='/'", ">home<", "default settlement"],
    "Start": ["/start", ">start<"],
    "Explorer": ["/explorer", ">explorer<"],
    "Specs": ["/spec", ">spec", "specification"],
    "GitHub": ["github.com", ">github<"],
}

CLI_LIFECYCLE = {
    "activate": ["defaultsettle activate"],
    "profile": ["defaultsettle profile"],
    "chain": ["defaultsettle chain"],
    "verify": ["defaultsettle verify"],
}

TERMINOLOGY = {
    "Default Settlement": ["default settlement"],
    "SAR": ["sar", "settlement attestation receipt"],
    "Continuity": ["continuity"],
    "Agent Profile": ["agent profile", "agent detail"],
    "Machine Trust": ["machine trust"],
    "Evidence Chain": ["evidence chain", "chained evidence", "chained receipt", "chain_id"],
    "Trust Report": ["trust report"],
}

EVIDENCE_LOOP_FIXTURES = [
    "activation-example.json",
    "continuity-receipt-example.json",
    "chain-complete-example.json",
    "agent-profile-example.json",
    "badge-verification-example.json",
]

EVIDENCE_LOOP_FIXTURE_NOTE = (
    "Evidence-loop fixture set detected: activation, continuity receipt, chain complete, "
    "agent profile, and badge verification."
)


@dataclass
class Surface:
    name: str
    kind: str
    source: str
    path: Path | None
    text: str
    raw: str
    ok: bool
    missing: bool = False


def latest_bundle(repo_root: Path) -> Path:
    audits_dir = repo_root / "reports" / "surface-audits"
    candidates = sorted([path for path in audits_dir.iterdir() if path.is_dir()])
    if not candidates:
        raise FileNotFoundError(f"No audit bundles found in {audits_dir}")
    return candidates[-1]


def html_to_text(raw: str) -> str:
    without_scripts = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
    without_tags = re.sub(r"(?s)<[^>]+>", " ", without_scripts)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def load_summary(bundle_dir: Path) -> dict[str, Any]:
    summary_path = bundle_dir / "summary.json"
    if summary_path.exists():
        return json.loads(read_text(summary_path))
    return {"urls": [], "local_files": []}


def surface_name_for_url(url: str) -> str:
    if url.rstrip("/") == "https://defaultverifier.com":
        return "Homepage"
    if url.endswith("/start"):
        return "Start"
    if url.endswith("/explorer"):
        return "Explorer"
    if "/fixtures/" in url:
        return "Fixtures"
    if "/spec/" in url:
        return "Specs"
    return url


def surface_name_for_local(path: str) -> str:
    if "README.md" in path:
        return "GitHub repos"
    if "fixtures" in path:
        return "Fixtures"
    if "spec/" in path:
        return "Specs"
    if "explorer" in path:
        return "Explorer"
    if "start" in path:
        return "Start"
    if "index.html" in path:
        return "Homepage"
    return "GitHub repos"


def load_surfaces(bundle_dir: Path, summary: dict[str, Any]) -> list[Surface]:
    surfaces: list[Surface] = []
    summary_md = bundle_dir / "summary.md"
    if summary_md.exists():
        raw = read_text(summary_md)
        surfaces.append(Surface("Collector Summary", "summary", "summary.md", summary_md, raw, raw, True))

    for item in summary.get("urls", []):
        output = Path(item["output"])
        raw = read_text(output) if output.exists() else ""
        surfaces.append(
            Surface(
                surface_name_for_url(item.get("url", "")),
                "url",
                item.get("url", str(output)),
                output if output.exists() else None,
                html_to_text(raw),
                raw,
                bool(item.get("ok")) and output.exists(),
            )
        )

    for item in summary.get("local_files", []):
        output = Path(item["output"])
        raw = read_text(output) if output.exists() else ""
        is_html = output.suffix.lower() in {".html", ".htm"}
        surfaces.append(
            Surface(
                surface_name_for_local(item.get("path", "")),
                "local",
                item.get("path", str(output)),
                output if output.exists() else None,
                html_to_text(raw) if is_html else raw,
                raw,
                bool(item.get("ok")) and output.exists(),
                bool(item.get("missing")),
            )
        )
    return surfaces


def contains_any(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def coverage(text: str, checks: dict[str, list[str]]) -> dict[str, bool]:
    return {name: contains_any(text, terms) for name, terms in checks.items()}


def grouped_surfaces(surfaces: list[Surface]) -> dict[str, list[Surface]]:
    groups = {
        "Homepage": [],
        "Start": [],
        "Explorer": [],
        "Specs": [],
        "Fixtures": [],
        "GitHub repos": [],
    }
    for surface in surfaces:
        if surface.name in groups:
            groups[surface.name].append(surface)
    return groups


def missing_names(items: dict[str, bool]) -> list[str]:
    return [name for name, present in items.items() if not present]


def cli_lifecycle_lines(status: dict[str, bool]) -> list[str]:
    labels = {
        "activate": "activate command",
        "profile": "profile command",
        "chain": "chain command",
        "verify": "verify command",
    }
    lines: list[str] = []
    for command, present in status.items():
        if present:
            lines.append(f"✓ {labels[command]} detected")
        elif command == "activate":
            lines.append(f"○ {labels[command]} pending onboarding")
        else:
            lines.append(f"✗ {labels[command]} missing")
    return lines


def fixture_coverage(bundle_dir: Path, surfaces: list[Surface], summary: dict[str, Any]) -> dict[str, bool]:
    searchable_parts: list[str] = []
    searchable_parts.extend(str(path.relative_to(bundle_dir)) for path in bundle_dir.rglob("*") if path.is_file())
    searchable_parts.extend(surface.source for surface in surfaces)
    searchable_parts.extend(str(surface.path) for surface in surfaces if surface.path)
    searchable_parts.extend(surface.raw for surface in surfaces if surface.ok)
    searchable_parts.extend(
        " ".join(str(value) for value in item.values())
        for section in ("local_files", "urls")
        for item in summary.get(section, [])
    )
    searchable_text = "\n".join(searchable_parts).lower()
    return {fixture: fixture.lower() in searchable_text for fixture in EVIDENCE_LOOP_FIXTURES}


def describe_surface(surface: Surface) -> str:
    if surface.missing:
        return f"`{surface.source}` was missing from the collector bundle."
    if not surface.ok:
        return f"`{surface.source}` could not be read successfully."

    accuracy = coverage(surface.text, CURRENT_ACCURACY)
    onboarding = coverage(surface.text, ONBOARDING)
    nav = coverage(surface.raw.lower(), NAVIGATION)
    terms = coverage(surface.text, TERMINOLOGY)

    notes: list[str] = []
    missing_accuracy = missing_names(accuracy)
    missing_onboarding = missing_names(onboarding)
    missing_nav = missing_names(nav)
    missing_terms = missing_names(terms)

    if missing_accuracy:
        notes.append(f"accuracy gaps: {', '.join(missing_accuracy)}")
    if missing_onboarding:
        notes.append(f"onboarding gaps: {', '.join(missing_onboarding)}")
    if missing_nav:
        notes.append(f"navigation gaps: {', '.join(missing_nav)}")
    if missing_terms:
        notes.append(f"terminology gaps: {', '.join(missing_terms)}")
    if not notes:
        notes.append("covers the core evidence-loop language well")

    return f"`{surface.source}`: " + "; ".join(notes) + "."


def has_any_surface(surfaces: list[Surface], terms: list[str]) -> bool:
    return any(surface.ok and contains_any(surface.text, terms) for surface in surfaces)


def build_report(bundle_dir: Path, surfaces: list[Surface], summary: dict[str, Any]) -> str:
    groups = grouped_surfaces(surfaces)
    missing_files = [item["path"] for item in summary.get("local_files", []) if item.get("missing")]
    all_text = "\n".join(surface.text for surface in surfaces if surface.ok)
    overall_terms = coverage(all_text, TERMINOLOGY)
    cli_status = coverage(all_text, CLI_LIFECYCLE)
    fixture_status = fixture_coverage(bundle_dir, surfaces, summary)
    missing_fixtures = missing_names(fixture_status)
    has_complete_fixture_set = not missing_fixtures

    p0: list[str] = []
    p1: list[str] = []
    p2: list[str] = []

    if missing_files:
        p0.append(
            "Fill missing repository READMEs captured by the collector: "
            + ", ".join(f"`{path}`" for path in missing_files)
            + ". These are public trust surfaces and currently create dead zones for GitHub evaluation."
        )
    if not has_any_surface(surfaces, ["public trust report", "trust report"]):
        p0.append(
            "Add Public Trust Report language and destination links. The canonical evidence loop ends in a public report, but the collected surfaces do not make that outcome visible."
        )
    if not has_any_surface(surfaces, ["machine trust"]):
        p0.append(
            "State the canonical category clearly on public entry points: Default Settlement is machine trust infrastructure for autonomous systems."
        )

    if not has_any_surface(surfaces, ["agent profile"]):
        p1.append(
            "Standardize Explorer copy around Agent Profiles, not only generic explorer or agent detail language."
        )
    if not has_any_surface(surfaces, ["badge verification", "badge"]):
        p1.append(
            "Expose Badge Verification as a named step between Explorer Agent Profile and Public Trust Report."
        )
    if not has_any_surface(surfaces, ["sdk", "cli"]):
        p1.append(
            "Add SDK or CLI pathing to developer onboarding. The current surfaces point to specs and APIs, but not a packaged integration path."
        )
    if not contains_any(all_text, ["github.com/default-settlement"]):
        p1.append(
            "Normalize GitHub navigation to the canonical Default Settlement organization where possible; collected pages mix organization and personal GitHub links."
        )

    p2.extend(
        [
            "Add copyable end-to-end examples for Agent Activation -> SAR Receipt -> Continuity Receipt -> Chained Evidence.",
            "Add a glossary block that keeps Default Settlement, SAR, Continuity, Agent Profile, Machine Trust, Evidence Chain, and Trust Report consistent across pages.",
        ]
    )
    if has_complete_fixture_set:
        p2.append(EVIDENCE_LOOP_FIXTURE_NOTE)
    else:
        p2.append(
            "Missing evidence-loop fixture files: "
            + ", ".join(f"`{fixture}`" for fixture in missing_fixtures)
            + "."
        )

    if not p0:
        p0.append("No blocking P0 surfaced from the collected bundle.")
    if not p1:
        p1.append("No major P1 gaps surfaced from the collected bundle.")

    lines = [
        "# Surface Audit Report",
        "",
        "## Executive Summary",
        "",
        f"Bundle audited: `{bundle_dir}`.",
        "",
        CANONICAL_STATE,
        "",
        "Current evidence loop: " + " -> ".join(EVIDENCE_LOOP) + ".",
        "",
        "The surfaces have solid SAR, Continuity, fixture, and Explorer foundations. The main product-strategy gap is that the public journey still reads more like verification documentation than a complete machine-trust activation loop. Agent Activation, chained evidence, and continuity receipts are present in parts, but Agent Profile, Badge Verification, and Public Trust Report need sharper public naming and navigation.",
        "",
    ]
    if has_complete_fixture_set:
        lines.extend([EVIDENCE_LOOP_FIXTURE_NOTE, ""])
    else:
        lines.extend(
            [
                "Evidence-loop fixture coverage is incomplete. Missing files: "
                + ", ".join(f"`{fixture}`" for fixture in missing_fixtures)
                + ".",
                "",
            ]
        )
    lines.append("Terminology coverage across the bundle:")
    lines.extend(f"- {term}: {'present' if present else 'missing'}" for term, present in overall_terms.items())

    lines.extend(["", "## CLI Lifecycle", ""])
    lines.extend(cli_lifecycle_lines(cli_status))
    if not cli_status["activate"]:
        lines.extend(
            [
                "",
                "Activate is tracked as pending onboarding because `defaultsettle activate` is planned but not implemented yet.",
            ]
        )

    lines.extend(["", "## P0 Fix Before Ecosystem Push", "", "(blocking)", ""])
    lines.extend(f"- {item}" for item in p0)

    lines.extend(["", "## P1 Important Improvements", ""])
    lines.extend(f"- {item}" for item in p1)

    lines.extend(["", "## P2 Future Improvements", ""])
    lines.extend(f"- {item}" for item in p2)

    lines.extend(["", "## Per Surface Review", ""])
    for group_name in ["Homepage", "Start", "Explorer", "Specs", "Fixtures", "GitHub repos"]:
        lines.extend([f"### {group_name}", ""])
        if not groups[group_name]:
            lines.append("- No collected surface found for this category.")
        else:
            lines.extend(f"- {describe_surface(surface)}" for surface in groups[group_name])
        lines.append("")

    lines.extend(
        [
            "## Recommended Codex Implementation Order",
            "",
            "1. Create or restore the missing README surfaces so GitHub repos participate in the trust story.",
            "2. Update Homepage and Start copy to state the canonical machine-trust category and full evidence loop.",
            "3. Update Explorer language to consistently name Agent Profiles, chained evidence, badge verification, and public trust reports.",
            "4. Normalize navigation across Home, Start, Explorer, Specs, and GitHub links.",
            "5. Add developer examples for activation, SAR, continuity, chain lookup, profile rendering, and trust-report verification.",
            "6. "
            + (
                "Keep the detected evidence-loop fixture set visible in public specs."
                if has_complete_fixture_set
                else "Add missing fixture coverage for " + ", ".join(missing_fixtures) + "."
            ),
            "7. Add SDK/CLI documentation after the public surface language is stable.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    repo_root = Path(__file__).resolve().parent
    try:
        bundle_dir = latest_bundle(repo_root)
        summary = load_summary(bundle_dir)
        surfaces = load_surfaces(bundle_dir, summary)
        report = build_report(bundle_dir, surfaces, summary)
        report_path = bundle_dir / "surface_audit_report.md"
        report_path.write_text(report, encoding="utf-8")
        print(report_path)
        return 0
    except Exception as error:
        print(f"surface_auditor.py: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
