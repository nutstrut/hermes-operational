"""Tests for delegated-identity attribution in task_runner.py.

These tests only exercise resolve_identity() / build_sar_input() /
build_continuity_input() -- pure functions with no network or filesystem
side effects. No task is ever run against a real attest_endpoint, and no
production task file is touched.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from task_runner import (  # noqa: E402
    HERMES_AGENT_ID,
    MissingAccountableAgentError,
    build_continuity_input,
    build_sar_input,
    resolve_identity,
)

MORPHEUS_AGENT_ID = "agent:morpheus"


def test_delegated_task_resolves_morpheus_as_accountable_subject():
    task = {"task_id": "hermes-verify-sar-spec-v1", "agent_id": MORPHEUS_AGENT_ID}

    identity = resolve_identity(task)

    assert identity["agent_id"] == MORPHEUS_AGENT_ID
    assert identity["executor_id"] == HERMES_AGENT_ID
    assert identity["execution_mode"] == "delegated"


def test_delegated_sar_input_carries_all_three_identity_fields():
    task = {"task_id": "hermes-verify-sar-spec-v1", "agent_id": MORPHEUS_AGENT_ID}
    identity = resolve_identity(task)

    sar_input = build_sar_input(task["task_id"], identity, "SAR", verified=True)

    assert sar_input["agent_id"] == MORPHEUS_AGENT_ID
    assert sar_input["executor_id"] == HERMES_AGENT_ID
    assert sar_input["execution_mode"] == "delegated"
    assert sar_input["output"] == {"expected_content_contains": "SAR"}


def test_missing_accountable_agent_id_fails_closed():
    task = {"task_id": "some-task-without-owner"}

    with pytest.raises(MissingAccountableAgentError):
        resolve_identity(task)


def test_missing_accountable_agent_id_error_names_the_task_not_hermes():
    task = {"task_id": "some-task-without-owner"}

    with pytest.raises(MissingAccountableAgentError) as excinfo:
        resolve_identity(task)

    message = str(excinfo.value)
    assert "some-task-without-owner" in message
    assert "agent_id" in message


def test_hermes_owned_task_resolves_to_self_mode():
    task = {"task_id": "hermes-self-check-v1", "agent_id": HERMES_AGENT_ID}

    identity = resolve_identity(task)

    assert identity["agent_id"] == HERMES_AGENT_ID
    assert identity["executor_id"] == HERMES_AGENT_ID
    assert identity["execution_mode"] == "self"

    sar_input = build_sar_input(task["task_id"], identity, "ok", verified=True)
    assert sar_input["agent_id"] == HERMES_AGENT_ID
    assert sar_input["executor_id"] == HERMES_AGENT_ID
    assert sar_input["execution_mode"] == "self"


def test_continuity_input_still_anchors_hermes_as_execution_environment():
    # The continuity input describes Hermes's own execution environment
    # continuity, independent of which agent is accountable for the task.
    continuity = build_continuity_input("task-1", {"url": "https://example.com"}, "ab" * 32)

    assert continuity["subject"]["subject_id"] == HERMES_AGENT_ID
    assert continuity["execution_path"]["executor_id"] == HERMES_AGENT_ID


def test_all_production_task_definitions_declare_an_agent_id():
    import glob
    import json

    tasks_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tasks")
    task_files = sorted(glob.glob(os.path.join(tasks_dir, "*.json")))
    assert task_files, "expected at least one production task definition"

    for path in task_files:
        with open(path) as f:
            task = json.load(f)
        assert task.get("agent_id"), f"{path} is missing a required 'agent_id'"
        # resolve_identity must not raise for any committed production task.
        identity = resolve_identity(task)
        assert identity["executor_id"] == HERMES_AGENT_ID
