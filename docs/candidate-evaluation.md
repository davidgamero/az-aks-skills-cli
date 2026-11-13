# Research candidate implementation and evaluation

## Frozen primary-fixture scope

The [17 researched candidates](research/scenario-candidates.json) are registered
as `suite=candidate-v1`, `variant=primary`. Each has one seeded resource graph,
ordinary CLI/kubectl repair operations, a separate desired-state oracle and a
host-only reference sequence. The benchmark catalog adds 16 procedures (the ACR
procedure serves two cases), for 25 skills total.

Both arms receive identical prompts and identical editable `/work/task-context.json`,
`workload.yaml` and `secret-provider-class.yaml`. The context supplies authorized
identifiers, limits and application probes. It does not disclose desired state or
scoring. Skill discovery remains through AKS help. State, oracles, references and
authoritative event logs remain host-owned outside the fresh containers.

These are **bounded simulations**, not Azure/Kubernetes conformance tests:

- One primary fault per candidate; held-out variants are not implemented or evaluated.
- Synchronous reconciliation; no real scheduler, admission webhook, token issuer,
  RBAC propagation delay, node provisioning or asynchronous controller timing.
- Standard ingress NetworkPolicy matchLabels/port union and same-peer intersection;
  Cilium policy types, IP blocks and matchExpressions are outside this fixture.
- ABAC StringEquals/ActionMatches boolean subset. Repository permissions are checked
  against approved and unapproved equivalence classes, not substring matching.
- NAP capacity uses fixed four-vCPU nodes and an aggregate dynamic pool ceiling.
  Image maintenance intentionally ends in `configured_with_evidenced_blocker`:
  schedule set, image drift observed, unchanged PDB still prohibits replacement.
- Gateway HTTP listeners, hostname/path, same-namespace references, Service ports
  and ready endpoints are modeled. TLS, cross-namespace grants and mesh migrations
  need separate coverage.
- CSI values are synthetic version sentinels. Env refresh is modeled as a rolling
  restart; arbitrary application commands and actual secret values are not executed.
- Unsupported commands/options are retained as coverage gaps and excluded from
  model-performance comparisons. No candidate operation delegates to Azure.

Final success requires state/invariant checks and fresh relevant observation after
the last change. PDB weakening/deletion, availability loss, namespace deletion,
broad repository grants and other prohibited transitions remain in history even
if the agent later restores the final configuration. Manual status fields cannot
forge controller readiness. Each candidate has an independent negative control;
additional tests cover temporal changes, resource deletion, policy union, ABAC
broadening, Gateway failures, uploaded manifests and stale verification.

## Validation and run recipe

```sh
python3 -m unittest discover -s tests -v
PYTHONPATH=bench .venv-bench/bin/python -m unittest discover -s bench/tests -v
PYTHONPATH=bench .venv-bench/bin/python bench/check_candidates.py \
  --bwrap /tmp/opencode/bubblewrap/usr/bin/bwrap \
  --copilot /home/david/.local/bin/copilot \
  --output benchmark-results/candidate-container-check
```

The container check executes reference operations, including manifest uploads and
approved live Learn/Kubernetes documentation GETs. It is replay evidence, not a
model trial. The local raw artifacts remain gitignored.

Live evaluation uses local Copilot `gpt-6.1-sol`, a matched baseline/skills pair per
primary fixture, discovery-only prompts, seed 19, and a 300-second timeout. The
runner freezes the catalog, records source hashes/revision, shuffles arm order,
retains failures and reports invalid trials separately. One pair is a smoke
evaluation, not an efficacy estimate. No content benefit can be attributed to an
unread skill. Other explicit model IDs and the optional Foundry provider remain
available.

Live results will be added after the frozen sweep and trace review.
