# OOAK × zkML (Community Example) — Trustless USDC Agents

This community example composes OOAK secure tools with zkML proofs so an agent can gate sensitive actions (like USDC transfers) behind verifiable checks.

- Example repo (by @hshadab): https://github.com/hshadab/agentkit/tree/main/Circle-OOAK
- OOAK launch blog (by Mira Belenkiy): https://www.circle.com/blog/ooak-object-oriented-agent-kit

## What It Shows
- Map tool inputs to features, run real ONNX inference, and map results to an approval signal.
- Generate Groth16 proofs for public signals (e.g., decision, confidence) and verify on-chain.
- Optionally bind a JOLT proof hash for proof-of-execution in the audit record.
- Execute a `@secure_tool` only after verifiable approval.

## Quickstart
Follow the README in the linked repo for setup and execution. At a high level:
1) Clone the `agentkit` repo and navigate to `Circle-OOAK`.
2) Provide environment variables (e.g., LLM/Chain) as instructed there.
3) Install dependencies and run the Python demo and/or Node UI.

## Notes
- Community-maintained; this does not change OOAK’s API or runtime.
- Issues with the example should be filed in the example repo.

## Maintainer
- Community example by @hshadab

