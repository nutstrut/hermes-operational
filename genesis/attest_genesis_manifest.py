import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ATTEST_ENDPOINT = "https://defaultverifier.com/v1/attest"
TASK_ID = "morpheus-genesis-import-manifest-v0.1"
MANIFEST_DISPLAY_PATH = "genesis/morpheus-genesis-import-v0.1.json"
MANIFEST_PATH = Path(__file__).with_name("morpheus-genesis-import-v0.1.json")
RECEIPTS_DIR = Path(__file__).with_name("receipts")


def receipt_id(receipt, *keys):
    for key in keys:
        value = receipt.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            nested_value = value.get("receipt_id") or value.get("id")
            if isinstance(nested_value, str):
                return nested_value
    return None


def extract_chain_id(receipt):
    chain = receipt.get("chain")
    if isinstance(chain, dict) and isinstance(chain.get("chain_id"), str):
        return chain["chain_id"]

    if isinstance(receipt.get("chain_id"), str):
        return receipt["chain_id"]

    raise KeyError("response did not include chain.chain_id or chain_id")


def post_json(url, payload):
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Hermes/1.0",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            response_body = response.read()
            return response.status, json.loads(response_body.decode("utf-8"))
    except HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        print(f"[hermes] status_code={error.code}")
        print(error_body)
        raise
    except URLError as error:
        raise RuntimeError(f"attestation request failed: {error.reason}") from error


def main():
    manifest_bytes = MANIFEST_PATH.read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))

    digest = hashlib.sha256(manifest_bytes).hexdigest()
    manifest_digest = f"sha256:{digest}"
    evaluated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    attested_manifest = {
        "manifest_path": MANIFEST_DISPLAY_PATH,
        "manifest_digest": manifest_digest,
        "manifest_type": manifest["manifest_type"],
        "activation_type": manifest["activation_type"],
        "expected_agent_id": manifest["agent_id"],
    }

    payload = {
        "continuity_input": {
            "schema_version": "0.1",
            "subject": {
                "subject_id": "agent:morpheus",
                "subject_type": "agent",
            },
            "receipts": [{
                "signal_type": "genesis_import_manifest",
                "digest": manifest_digest,
                "issuer": "hermes-operational",
            }],
            "execution_path": {
                "action_id": TASK_ID,
                "requested_action": attested_manifest,
                "admitted_action": attested_manifest,
                "executed_action": attested_manifest,
                "mutation_boundary_ts": evaluated_at,
                "executor_id": "agent:morpheus",
                "execution_environment": {
                    "name": "defaultverifier-production",
                    "runtime": "python",
                },
            },
            "mutation_events": [],
            "evaluation_context": {
                "evaluated_at": evaluated_at,
                "policy_ref": "morpheus-genesis-import-manifest-v0.1",
                "expected_verifier_id": "defaultverifier-continuity-v1",
            },
        },
        "sar_input": {
            "task_id": TASK_ID,
            "agent_id": "agent:morpheus",
            "spec": attested_manifest,
            "output": attested_manifest,
            "counterparty": "defaultsettlement",
        },
    }

    status_code, receipt = post_json(ATTEST_ENDPOINT, payload)
    chain_id = extract_chain_id(receipt)

    RECEIPTS_DIR.mkdir(exist_ok=True)
    saved_path = RECEIPTS_DIR / f"{chain_id}.json"
    saved_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    print(f"[hermes] status_code={status_code}")
    print(f"[hermes] manifest_digest={manifest_digest}")
    print(f"[hermes] sar_receipt_id={receipt_id(receipt, 'sar_receipt_id', 'sar_receipt', 'sar')}")
    print(
        "[hermes] continuity_receipt_id="
        f"{receipt_id(receipt, 'continuity_receipt_id', 'continuity_receipt', 'continuity')}"
    )
    print(f"[hermes] chain_id={chain_id}")
    print(f"[hermes] saved_path={saved_path.as_posix()}")


if __name__ == "__main__":
    main()
