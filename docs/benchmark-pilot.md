# Initial GPT-6.1 Sol pilot — November 12, 2026

## Result

The harness worked, but this small pilot **did not show an overall efficiency
benefit from the skills**. All tasks succeeded in both arms. Guided retrieval
added model calls and elapsed time. Passive availability did not cause discovery
in the two tasks tested.

These are live Copilot results from isolated rootless Linux containers, not
reference-script replays. The model was requested as `gpt-6.1-sol` and confirmed
by Copilot's exported inference spans. Copilot CLI version: **1.0.98**.

## Guided-use experiment

Five matched pairs, one seed per scenario (`seed=1`), with order shuffled per pair.
Only the skills arm received the instruction to consult the CLI runbooks. Both
arms used the same fixture, service delays, model and container setup. The skills
arm used the repository's actual skill CLI parser and renderer with `bench/skills`.

| Scenario | Baseline seconds | Skills seconds | Baseline / skills modeled Azure requests | Baseline / skills model inference spans |
|---|---:|---:|---:|---:|
| Fixed-size pool | 13.26 | 19.69 | 8 / 10 | 4 / 7 |
| Autoscaler bounds | 12.21 | 17.08 | 5 / 7 | 3 / 5 |
| Control-plane-only upgrade | 16.22 | 16.93 | 7 / 6 | 4 / 5 |
| Stop development cluster | 12.66 | 16.63 | 5 / 5 | 3 / 6 |
| Scaling with injected 429 | 23.11 | 25.52 | 9 / 11 | 6 / 9 |
| **Sum across these five tasks** | **77.47** | **95.86** | **34 / 39** | **20 / 32** |

- State-based success, including verification reads: **5/5 baseline, 5/5 skills**.
- Successful skill reads: **5/5 treatment runs**, one document per run.
- Simulated Azure CLI operations: **20 baseline, 25 skills**.
- Coverage gaps: **zero**; every container passed its containment preflight.
- Times include container/Copilot startup, inference, tools and final response.
- Service delays were **30 ms per modeled operation** plus **150 ms per synchronous
  state change**. These seconds are not real Azure provisioning durations.

### What the traces showed

In four of the five treatment runs, the agent tried both:

```text
az aks skill search --query "..."
az aks skill show SKILL-ID
```

The interface requires a positional search string and `show --name SKILL-ID`.
These eight failed local calls cost no modeled Azure requests, but created extra
tool/inference work. Sol recovered and successfully read the relevant skill in
every treatment run.

Some skill runs also repeated inspections or explicitly checked the unchanged
system pool. The control-plane upgrade was the one task with fewer modeled Azure
requests in the treatment: four simulated Azure commands versus five baseline.
Its skill retrieval still added an inference span and about 0.7 seconds in this
single pair.

The guided prompt itself, retrieval, parser discoverability and skill content all
contribute to this treatment effect. This experiment does not isolate the prose
quality of a skill from the cost of finding and retrieving it.

## Passive-discovery experiment

Two additional matched pairs used **identical prompts** in both arms. Treatment
help advertised the skill command group, but the task prompt did not mention it.

| Scenario | Baseline seconds | Skills-available seconds | Baseline / treatment modeled Azure requests | Skill calls in treatment |
|---|---:|---:|---:|---:|
| Fixed-size pool | 12.06 | 12.11 | 8 / 8 | 0 |
| Control-plane-only upgrade | 13.97 | 15.60 | 7 / 7 | 0 |

All four tasks succeeded. There were **no skill calls**, so these timings do not
measure skill usefulness: the agent followed the ordinary CLI workflow in both
arms. Two cases are insufficient to estimate a general discovery/adoption rate.

## Evidence and reproducibility

Full artifacts are local and gitignored:

```text
benchmark-results/sol-pilot/     # 10 guided live trials
benchmark-results/sol-passive/   # 4 passive live trials
```

Each directory contains `run.json`, machine-readable and Markdown summaries, and
per-trial state, CLI trace, human-readable timeline, Copilot output, OTel, proxy
trace and isolation checks. Only this aggregate summary is committed.

Command manifest SHA-256:
`a6f6dcbfdaea4fbef5e35ba73dcaab9a068bc9429a1a45cccb120c117541a50f`.

The runs occurred during development on top of Git revision
`287d94dc298ceaefbb852b6effaf36f278fed414`, with a dirty working tree recorded in
both manifests. Benchmark source fingerprints at launch:

- Guided: `86c9ed8362ec1e4764361f0b11894a56fe1eb64274b89e870bfb938bacc0f158`
- Passive: `209d71f23ae8c46808da7fee25bdc155a9aa687ac69471c6d49ab83d1d581e3d`

Reporting/metadata tests were improved between runs; scenarios and skill content
were unchanged. The earlier `sol-smoke` debugging run used an interim skill-output
adapter and is deliberately excluded from this pilot comparison. Subsequent
efficacy runs should use a committed, frozen version rather than a development
working tree.

The Azure request figures are a documented **simulation cost model**, not captured
ARM traffic. No Azure resource operation was sent to Azure. Actual model request
evidence comes from OTel inference spans; proxy TLS connections/bytes are tracked
separately. The optional Foundry path and Docker engine were not live-tested:
these runs used GitHub-hosted Copilot and rootless Bubblewrap containers.

## Recommended next controlled experiments

1. **Interface affordances:** test a separate variant supporting positional `show`
   or including executable usage examples in list/help. Keep `--query` semantics
   explicit because Azure CLI already uses that name for JMESPath filtering.
2. **Content efficiency:** test guidance that reuses already-returned state rather
   than repeating broad inspections. Preserve final verification and invariants.
3. **Knowledge-sensitive tasks:** add realistic quota, identity, version-skew and
   upgrade-precondition failures whose correct recovery is not trivial for this
   model. Implement their state model and independent oracle first.
4. **Discovery:** compare passive help, a short global capability hint, and
   explicit retrieval as separate conditions.
5. **Replication:** freeze versions and run 10–20 or more matched seeds per task
   and model; report paired distributions and confidence intervals alongside
   success rates. Use latency sensitivity runs before making production-time claims.

The current data supports debugging the interface and experiment design. It does
not establish statistical significance, reliable adoption, or a production
performance gain or regression.
