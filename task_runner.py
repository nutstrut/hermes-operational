import json
import hashlib
import pathlib
import urllib.request
import requests
import sys

TASK_PATH = sys.argv[1]

task = json.load(open(TASK_PATH))

task_id = task["task_id"]
spec = task["spec"]

url = spec["url"]
expected = spec["expected_content_contains"]

print(f"[hermes] fetching: {url}")

content = urllib.request.urlopen(url).read()
text = content.decode("utf-8")

sha256 = hashlib.sha256(content).hexdigest()

contains_expected = expected in text

print(f"[hermes] sha256={sha256}")
print(f"[hermes] contains_expected={contains_expected}")

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
        "spec": {
            "expected_content_contains": expected
        },
        "output": {
            "expected_content_contains": expected
        } if contains_expected else {
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