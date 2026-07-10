import json
import hashlib
import pathlib
import urllib.request
import requests
import sys
from json_helper import json_path_values

# Hermes's own canonical identity. This is the executor identity for every
# receipt Hermes submits -- it is never the default accountable subject.
HERMES_AGENT_ID = "0xf23C8C0695e0Bd7c6eB979AEc128386Bf1ce3dCc:hermes"


class MissingAccountableAgentError(ValueError):
    """Raised when a task definition does not declare its accountable agent_id.

    Accountability must never default to Hermes. A task without an explicit
    accountable agent_id is a configuration error, not something Hermes should
    guess its way around.
    """


def resolve_identity(task: dict) -> dict:
    """Resolve accountable subject / executor / execution_mode for a task.

    agent_id       -- accountable task owner; receives TrustScore attribution.
    executor_id    -- Hermes's own canonical identity (who actually ran the task).
    execution_mode -- "delegated" when the accountable agent is not Hermes itself,
                       "self" when Hermes is its own accountable subject.

    Fails closed: raises MissingAccountableAgentError rather than defaulting
    the accountable agent to Hermes.
    """
    agent_id = task.get("agent_id")
    if not agent_id:
        raise MissingAccountableAgentError(
            f"task {task.get('task_id')!r} has no 'agent_id' (accountable subject); "
            "refusing to submit a receipt rather than defaulting attribution to Hermes"
        )
    execution_mode = "self" if agent_id == HERMES_AGENT_ID else "delegated"
    return {
        "agent_id": agent_id,
        "executor_id": HERMES_AGENT_ID,
        "execution_mode": execution_mode,
    }


def build_continuity_input(task_id: str, spec: dict, sha256: str) -> dict:
    return {
        "schema_version": "0.1",
        "subject": {
            "subject_id": HERMES_AGENT_ID,
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
            "executor_id": HERMES_AGENT_ID,
            "execution_environment": {
                "name": "defaultverifier-vps",
                "runtime": "python"
            }
        },
        "mutation_events": [],
        "evaluation_context": {
            "evaluated_at": "2026-05-14T20:00:00Z",
            "policy_ref": "hermes-http-fetch-v1",
            "expected_verifier_id": "defaultverifier-continuity-v1"
        }
    }


def build_sar_input(task_id: str, identity: dict, expected: str, verified: bool) -> dict:
    return {
        "task_id": task_id,
        "agent_id": identity["agent_id"],
        "executor_id": identity["executor_id"],
        "execution_mode": identity["execution_mode"],
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


def run(task_path: str) -> None:
    task = json.load(open(task_path))

    task_id = task["task_id"]
    spec = task["spec"]

    # Resolve and validate accountable identity before doing any network work.
    identity = resolve_identity(task)

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
    print(
        f"[hermes] agent_id={identity['agent_id']} "
        f"executor_id={identity['executor_id']} "
        f"execution_mode={identity['execution_mode']}"
    )

    payload = {
        "continuity_input": build_continuity_input(task_id, spec, sha256),
        "sar_input": build_sar_input(task_id, identity, expected, verified),
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


if __name__ == "__main__":
    try:
        run(sys.argv[1])
    except MissingAccountableAgentError as e:
        print(f"[hermes] ERROR: {e}", file=sys.stderr)
        sys.exit(1)
