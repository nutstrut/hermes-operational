import json
import pathlib
import subprocess
import sys
import datetime

started_at = datetime.datetime.utcnow().isoformat() + "Z"
tasks = sorted(pathlib.Path("tasks").glob("*.json"))
pathlib.Path("reports").mkdir(exist_ok=True)

results = []
failed = 0
for task in tasks:
    print(f"\n[hermes] running task: {task}")
    result = subprocess.run(
        [sys.executable, "task_runner.py", str(task)],
        capture_output=True,
        text=True
    )

    print(result.stdout)
    if result.stderr:
        print(result.stderr)

    chain_id = None
    for line in result.stdout.splitlines():
        if line.startswith("[hermes] chain_id="):
            chain_id = line.split("=", 1)[1].strip()

    ok = result.returncode == 0
    if not ok:
        failed += 1

    results.append({
        "task": str(task),
        "ok": ok,
        "returncode": result.returncode,
        "chain_id": chain_id
    })
finished_at = datetime.datetime.utcnow().isoformat() + "Z"

report = {
    "agent_id": "0xf23C8C0695e0Bd7c6eB979AEc128386Bf1ce3dCc:hermes",
    "started_at": started_at,
    "finished_at": finished_at,
    "status": "pass" if failed == 0 else "fail",
    "total": len(tasks),
    "failed": failed,
    "results": results
}

stamp = finished_at.replace(":", "").replace(".", "")
report_path = f"reports/hermes-monitor-{stamp}.json"

with open(report_path, "w") as f:
    json.dump(report, f, indent=2)

with open("reports/latest.json", "w") as f:
    json.dump(report, f, indent=2)

print(f"\n[hermes] report saved: {report_path}")
print(f"[hermes] latest report: reports/latest.json")
print(f"[hermes] complete. total={len(tasks)} failed={failed}")

sys.exit(1 if failed else 0)
