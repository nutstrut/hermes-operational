import pathlib
import subprocess
import sys

tasks = sorted(pathlib.Path("tasks").glob("*.json"))

if not tasks:
    print("[hermes] no tasks found")
    sys.exit(1)

failed = 0

for task in tasks:
    print(f"\n[hermes] running task: {task}")
    result = subprocess.run([sys.executable, "task_runner.py", str(task)])
    if result.returncode != 0:
        failed += 1
        print(f"[hermes] task failed: {task}")

print(f"\n[hermes] complete. total={len(tasks)} failed={failed}")

sys.exit(1 if failed else 0)
