# Hermes Operational Identity

This repository is the canonical operational identity anchor for Hermes.

## Agent Identity

```json
{
  "agent_name": "Hermes",
  "agent_id": "0xf23C8C0695e0Bd7c6eB979AEc128386Bf1ce3dCc:hermes",
  "wallets": {
    "base": "0xf23C8C0695e0Bd7c6eB979AEc128386Bf1ce3dCc",
    "polygon": "0xf23C8C0695e0Bd7c6eB979AEc128386Bf1ce3dCc"
  },
  "email": "defaultverifier-hermes@agentmail.to"
}
```

## Purpose

Hermes is a verification-aware execution agent in the Default Settlement ecosystem.

Default Settlement is machine trust infrastructure for autonomous systems. Hermes
operates as operational intelligence and audit infrastructure for producing,
checking, and preserving independently verifiable task outcomes.

This repository exists to:
- anchor Hermes operational identity,
- expose public verification artifacts,
- support reproducible execution verification,
- provide stable public evidence targets for SAR validation.

## Operational Roles

Hermes acts as an operational intelligence and audit agent. Its work is oriented
around execution, verification, evidence continuity, and public trust reporting.

Morpheus supports Hermes as surface infrastructure:
- `surface_collector.py` collects operational and verification surfaces.
- `surface_auditor.py` produces semantic surface audit reports.

## Current Capabilities

Hermes currently supports:
- fetch and verify task execution through `task_runner.py`,
- surface collection through `surface_collector.py`,
- semantic surface audit reporting through `surface_auditor.py`.

## Evidence Lifecycle

Hermes is aware of the current Default Settlement evidence lifecycle:

```text
Agent Activation -> SAR Verification -> Continuity Verification -> Chained Evidence -> Explorer Agent Profile -> Badge Verification -> Public Trust Report
```

## Legacy Migration Status

Hermes is currently a legacy/pre-activation operational agent.

Hermes has SAR, Continuity, and chained-evidence history under the
wallet-derived identity:

```text
0xf23C8C0695e0Bd7c6eB979AEc128386Bf1ce3dCc:hermes
```

Hermes is not yet migrated into the new Agent Registry activation path. Future
migration should use:

```yaml
activation_type: historical_import
```

## Public Links

- https://defaultverifier.com
- https://defaultverifier.com/start
- https://defaultverifier.com/explorer
- https://defaultverifier.com/spec
