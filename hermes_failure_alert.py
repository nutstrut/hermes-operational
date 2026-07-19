"""Hermes monitor failure alert notifier.

Triggered via systemd OnFailure= from hermes-monitor.service, or invoked
manually with --test to validate the alert path. Sends at most one email per
invocation through the existing Keith operator-email lane (the same SMTP
config and operator allowlist used by morpheus_send_morning_report.py /
morpheus_send_outbox_email.py in the morpheus repo), and always writes a
durable local record first -- before any email is attempted -- so the
failure is captured even if delivery fails.

This script never repairs, retries, restarts, or authorizes anything. Every
notification is explicitly labeled attention-only. No credentials, request
payloads, or environment values are included in the alert or the local
record; only safe operational fields are captured.
"""

from __future__ import annotations

import argparse
import json
import smtplib
import socket
import subprocess
import sys
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ALERT_REPORT_DIR = ROOT / "reports" / "alerts"
LATEST_REPORT_PATH = ROOT / "reports" / "latest.json"

# Read-only reuse of the existing Keith operator-email lane. This script
# never writes to the morpheus repo and introduces no new credential.
MORPHEUS_ROOT = Path("/home/ubuntu/morpheus")
EMAIL_ENV_FILE = MORPHEUS_ROOT / ".secrets" / "morpheus-email.env"
OPERATOR_RECIPIENTS_PATH = MORPHEUS_ROOT / "config" / "operator_email_recipients.json"

WATCHED_UNIT_DEFAULT = "hermes-monitor.service"

AUTHORITY_REMINDER = (
    "Attention only — this notification does not authorize repair, "
    "retry, restart, deployment, or any other action."
)


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def filename_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_shell_env_file(path: Path) -> dict:
    """Parse an `export KEY=value` shell env file without sourcing/executing it."""
    env: dict = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        env[key] = value
    return env


def operator_recipients() -> set:
    if not OPERATOR_RECIPIENTS_PATH.exists():
        return set()
    data = json.loads(OPERATOR_RECIPIENTS_PATH.read_text(encoding="utf-8"))
    return {
        str(a).strip().lower()
        for a in data.get("operator_recipients", [])
        if str(a).strip()
    }


def smtp_config() -> dict:
    env = load_shell_env_file(EMAIL_ENV_FILE)
    port_value = env.get("MORPHEUS_SMTP_PORT", "")
    try:
        port = int(port_value) if port_value else None
    except ValueError:
        port = None
    return {
        "host": env.get("MORPHEUS_SMTP_HOST"),
        "port": port,
        "user": env.get("MORPHEUS_SMTP_USER"),
        "password": env.get("MORPHEUS_SMTP_PASSWORD"),
        "from_addr": env.get("MORPHEUS_EMAIL_FROM"),
        "to_addr": env.get("MORPHEUS_EMAIL_TO"),
    }


def validate_smtp_config(config: dict) -> list:
    missing = []
    for key in ("host", "port", "user", "password", "from_addr", "to_addr"):
        if not config.get(key):
            missing.append(key)
    return missing


def systemd_unit_status(unit: str) -> dict:
    fields = "Result,ExecMainStatus,ActiveState,SubState"
    try:
        proc = subprocess.run(
            ["systemctl", "show", unit, f"--property={fields}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        out = proc.stdout
    except Exception as exc:  # pragma: no cover - defensive only
        return {"error": f"systemctl show failed: {type(exc).__name__}"}
    result: dict = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            result[k] = v
    return result


def latest_report_summary() -> dict:
    if not LATEST_REPORT_PATH.exists():
        return {"available": False}
    try:
        data = json.loads(LATEST_REPORT_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"available": False, "error": f"unreadable: {type(exc).__name__}"}
    return {
        "available": True,
        "status": data.get("status"),
        "total": data.get("total"),
        "failed": data.get("failed"),
        "finished_at": data.get("finished_at"),
    }


def build_alert_record(mode: str, unit: str, unit_status: dict, report_summary: dict) -> dict:
    return {
        "alert_id": f"hermes-alert-{mode.lower()}-{filename_timestamp()}",
        "created_at": iso_now(),
        "mode": mode,  # "TEST" or "FAILURE"
        "host": socket.gethostname(),
        "unit": unit,
        "unit_result": unit_status.get("Result"),
        "unit_exec_main_status": unit_status.get("ExecMainStatus"),
        "unit_active_state": unit_status.get("ActiveState"),
        "unit_sub_state": unit_status.get("SubState"),
        "latest_report_summary": report_summary,
        "email_attempted": False,
        "email_sent": False,
        "email_notes": [],
        "authority_reminder": AUTHORITY_REMINDER,
    }


def write_alert_record(record: dict) -> Path:
    ALERT_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = ALERT_REPORT_DIR / (record["alert_id"] + ".json")
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return path


def build_email(record: dict, record_path: Path, recipient: str, from_addr: str) -> EmailMessage:
    mode = record["mode"]
    subject = f"{'TEST' if mode == 'TEST' else 'FAILURE'} — Hermes monitoring alert path ({record['unit']})"
    summary = record["latest_report_summary"]
    lines = []
    if mode == "TEST":
        lines.append("No production failure is being reported. This is a test of the alert path only.")
        lines.append("")
    lines += [
        f"Mode: {mode}",
        f"Host: {record['host']}",
        f"Unit: {record['unit']}",
        f"Timestamp (UTC): {record['created_at']}",
        f"systemd Result: {record.get('unit_result')}",
        f"systemd ExecMainStatus: {record.get('unit_exec_main_status')}",
        "",
        "Latest Hermes report summary:",
        f"  status: {summary.get('status')}",
        f"  total: {summary.get('total')}",
        f"  failed: {summary.get('failed')}",
        f"  finished_at: {summary.get('finished_at')}",
        "",
        f"Local durable record: {record_path}",
        "",
        AUTHORITY_REMINDER,
    ]
    body = "\n".join(lines)
    message = EmailMessage()
    message["From"] = from_addr
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    return message


def send_email(message: EmailMessage, config: dict) -> None:
    host = str(config["host"])
    port = int(config["port"])
    user = str(config["user"])
    password = str(config["password"])
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
            smtp.login(user, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(user, password)
            smtp.send_message(message)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send a Hermes monitor failure alert. Attention only -- never repairs, retries, or restarts anything."
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Send a clearly labeled TEST alert instead of a FAILURE alert.",
    )
    parser.add_argument(
        "--unit",
        default=WATCHED_UNIT_DEFAULT,
        help="Unit name to report status for (default: hermes-monitor.service).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mode = "TEST" if args.test else "FAILURE"

    unit_status = systemd_unit_status(args.unit)
    report_summary = latest_report_summary()
    record = build_alert_record(mode, args.unit, unit_status, report_summary)

    # The durable local record is written before any email attempt, so the
    # failure (or test) is captured even if delivery fails entirely below.
    record_path = write_alert_record(record)
    print(f"[hermes-alert] mode={mode} local record: {record_path}")

    config = smtp_config()
    recipients = operator_recipients()
    to_addr = str(config.get("to_addr") or "").strip().lower()

    if not recipients:
        record["email_notes"].append("refused: no operator allowlist entries configured")
        write_alert_record(record)
        print("[hermes-alert] refused: no operator allowlist entries configured", file=sys.stderr)
        return 1

    if to_addr not in recipients:
        record["email_notes"].append("refused: configured recipient is not in the operator allowlist")
        write_alert_record(record)
        print("[hermes-alert] refused: configured recipient is not in the operator allowlist", file=sys.stderr)
        return 1

    missing = validate_smtp_config(config)
    if missing:
        record["email_notes"].append("not sent: missing SMTP config: " + ", ".join(missing))
        write_alert_record(record)
        print("[hermes-alert] not sent: missing SMTP config: " + ", ".join(missing), file=sys.stderr)
        return 1

    message = build_email(record, record_path, str(config["to_addr"]), str(config["from_addr"]))
    record["email_attempted"] = True
    try:
        send_email(message, config)
        record["email_sent"] = True
        record["email_notes"].append("sent")
        write_alert_record(record)
        print("[hermes-alert] email sent")
        return 0
    except Exception as exc:
        record["email_sent"] = False
        record["email_notes"].append(f"send failed: {type(exc).__name__}")
        write_alert_record(record)
        print(f"[hermes-alert] email send failed: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
