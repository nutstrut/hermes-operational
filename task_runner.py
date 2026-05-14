import json
import hashlib
import pathlib
import urllib.request
import requests
import sys
from json_helper import json_path_values

TASK_PATH = sys.argv[1]

task = json.load(open(TASK_PATH))

task_id = task["task_id"]
spec = task["spec"]

url = spec["url"]
expected = spec["expected_content_contains"]

print(f"[hermes] fetching: {url}")

req = urllib.request.Request(url, headers={"User-Agent": "Hermes/1.0"})
content = urllib.request.urlopen(req).read()
text = content.decode("utf-8")

sha256 = hashlib.sha256(content).hexdigest()

contains_expected = expected in text
json_checks_pass = True
if "expected_json_contains" in spec:
    data = json.loads(text)
    for path, required_values in spec["expected_json_contains"].items():
        actual_values = json_path_values(data, path)
        for required in required_values:
            if required not in actual_values:
                json_checks_pass = False
verified = contains_expected and json_checks_pass

print(f"[hermes] sha256={sha256}")
print(f"[hermes] contains_expected={contains_expected}")
print(f"[hermes] json_checks_pass={json_checks_pass}")
print(f"[hermes] verified={verified}")

payload = {
    "continuity_input": {
        "schema_version": "0.1",
        "subject": {
            "subject_id": "0xf23C8C0695e0Bd7c6eB979AEc128386Bf1ce3dCc:hermes",
            "subject_type": "agent"
        },
        "receipts": [{
            "receipt_id": f"{task_id}-root",
            "issuer": "hermes-operational",
            "signal_type": "governance_attestation",
            "digest": "sha256:" + sha256,
            "prior_signal_digest": None,
            "canonicalization_profile": "JCS",
            "signed_payload": {},
            "signature": {}
        }],
        "execution_path": {
            "action_id": task_id,
            "requested_action": spec,
            "admitted_action": spec,
            "executed_action": spec,
            "mutation_boundary_ts": "2026-05-14T20:00:00Z",
            "executor_id": "0xf23C8C0695e0Bd7c6eB979AEc128386Bf1ce3dCc:hermes",
            "execution_environment": {
                "name": "defaultverifier-vps",
                "runtime": "python"
            }
        },        "mutation_events": [],
        "evaluation_context": {
            "evaluated_at": "2026-05-14T20:00:00Z",
            "policy_ref": "hermes-http-fetch-v1",
            "expected_verifier_id": "defaultverifier-continuity-v1"
        }
    },
    "sar_input": {
        "task_id": task_id,
        "agent_id": "0xf23C8C0695e0Bd7c6eB979AEc128386Bf1ce3dCc:hermes",
        "spec": {
            "expected_content_contains": expected
        },
        "output": {
            "expected_content_contains": expected
        } if verified else {
            "expected_content_contains": "__MISMATCH__"
        },
        "counterparty": "0xf23C8C0695e0Bd7c6eB979AEc128386Bf1ce3dCc"
    }
}

endpoint = task["attest_endpoint"]

print(f"[hermes] submitting to {endpoint}")

r = requests.post(endpoint, json=payload, timeout=30)

print(f"[hermes] status_code={r.status_code}")

r.raise_for_status()

receipt = r.json()

chain_id = receipt["chain"]["chain_id"]

pathlib.Path("receipts").mkdir(exist_ok=True)

out_path = f"receipts/{chain_id}.json"

with open(out_path, "w") as f:
    json.dump(receipt, f, indent=2)

print(f"[hermes] saved receipt: {out_path}")
print(f"[hermes] chain_id={chain_id}")