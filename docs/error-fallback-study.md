# Skill usefulness, discoverability and consecutive-error fallback

## Questions and research basis

This study separates three things that earlier trials conflated:

1. **Capability:** does a procedure supply knowledge the agent otherwise lacks?
2. **Discovery:** does the agent encounter and retrieve that procedure?
3. **Failure response:** after repeated tool errors, does it seek a procedure, retry,
   change its approach, or stop with an evidenced blocker?

### Research reviewed on November 16, 2026

[Five primary-source snapshots](research/skill-efficacy-sources.json) were archived
with timestamps and SHA-256 hashes under
`benchmark-results/skill-efficacy-sources-20261116`. Papers are pinned to explicit
versions; vendor articles are the fetched revisions. The local snapshot manifest
SHA-256 is `bf34f5f496acb868376c0ce574ed29b032db6b7e49f38ae7789525b1adb573c7`.

- [SkillsBench v4](https://arxiv.org/abs/2602.12670v4) reports heterogeneous gains
  for curated skills on 87 expertise-heavy tasks across eight domains and 18
  model/harness configurations. Its reported aggregate improvement (33.9% to
  50.5%) is not an AKS result and not a prediction for GPT-6.1 Sol. Its task and
  harness differ from ours. Focused procedural modules are more promising than
  exhaustive generic documentation.
- [SWE-Skills-Bench v2](https://arxiv.org/abs/2603.15401v2) reports almost no average
  uplift (76.6% to 76.9%) and no statistically significant effect for 92/98 skills
  in its software-engineering evaluation. Some useful procedures addressed omitted
  steps; harmful ones overrode task requirements. This is a different benchmark,
  not a contradiction to resolve by averaging its score with SkillsBench.
- [Anthropic's skill architecture](https://www.anthropic.com/research/equipping-agents-for-the-real-world-with-agent-skills)
  exposes installed skill descriptions at startup, then loads relevant bodies and
  supporting scripts on demand. Our help-only CLI interface is a **different and
  less visible discovery mechanism**; conclusions about it do not generalize to
  native installed skills.
- [AKS skill source review](investigation-discovery.md) identifies deep Day-2
  procedures, packet capture, GPU ownership/telemetry, and organization-specific
  workflows as intended uses. Our earlier Sol baselines still identified all seven
  bounded investigation causes, while contextual references produced 4/7 skill
  reads versus 0/7 help-only. That established reach, not causal content benefit.
- [ARM throttling guidance](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/request-limits-and-throttling)
  and [retry-storm guidance](https://learn.microsoft.com/en-us/azure/architecture/antipatterns/retry-storm/)
  favor bounded retries/backoff and honoring Retry-After. A skill cannot restore an
  unavailable service. Stopping safely can be appropriate; retrieving a skill is
  not inherently better than a correct retry or handoff.

### Problem classes: ranked hypotheses, not claimed AKS efficacy

| Problem class | Why a skill might help | AKS example | How to test actual value |
|---|---|---|---|
| Organization-specific procedures and invariants | Not inferable from general pretraining | GitOps source of truth, approved failover order, data reconciliation and escalation | Same underlying runbooks in both arms; held-out incidents; score policy/data preservation |
| Specialist tools and uncommon evidence formats | Encodes working commands, parsers and applicability checks | Time-bounded multi-node pcap collection, GPU-specific telemetry, correlated log joins | Realistic artifacts and missing evidence; compare correct evidence/effort, not labels alone |
| Evolving version/ownership/support matrices | Training knowledge may be stale or overgeneralized | Managed versus customer GPU stack, migration eligibility and rollback constraints | Pin versions/sources; change held-out combinations; prevent unsupported actions |
| Long dependency chains with costly omitted steps | Checklists can improve consistency despite known commands | Upgrade readiness, stateful recovery, staged traffic migration | Temporal invariants, approval boundaries, rollback and end-to-end verification |
| Reusable deterministic computation | Bundled validated code can beat rewriting brittle logic | CIDR/capacity arithmetic, quota accounting, trace reduction | Same tool capability baseline; compare errors/time and input variants |
| Familiar CRUD or a single named misconfiguration | Little new procedural information | Fixed pool size, obvious role/FIC/alias repair | Existing baseline results suggest low headroom for Sol |
| Pure transient service/CLI outage | Missing availability, not missing domain knowledge | ARM 503 or repeated CLI exception | Measure safe retries/discovery separately; do not claim skills fix availability |

### What the existing local evaluations establish

| Observation | Supported conclusion | Not established |
|---|---|---|
| Earlier primary repair suite: 16/17 versus 17/17 latest audited completions, no reads | Familiar operations offered little measured headroom; availability alone did not elicit content use | That unread skills caused the one-task difference |
| Latest investigation suite: all seven baseline cause/candidate labels correct | Even the deeper bounded fixtures were within Sol's capabilities | That all real GPU/network investigations are easy or skills have no value |
| Contextual diagnostic references: 4/7 reads, help-only 0/7 | Actual diagnostic tools can provide a reachable discovery surface | A statistically reliable adoption uplift or a task-success improvement |
| Earlier provider-recovery sessions retrieved skills after registration was already repaired | Retrieval may support later workflow/verification rather than cause the repair | That the initial error triggered effective fallback before recovery |

These are different development runs and should not be pooled as a single trial
population. The error ladder adds a controlled manipulation of failure count,
rather than inferring a threshold from unrelated tasks that happened to fail.

### Recommended capability study after the discovery experiment

The most promising missing information is **specific procedural knowledge**, not
more errors. Promote a problem class only after a no-skills prescreen shows a
repeatable omission and a held-out test can verify it. Examples:

- **GitOps-aware stateful recovery:** the easy visible patch is reconciled away;
  durable recovery requires the source repository and application-level data
  checks, not just Kubernetes readiness. Score restored state, correct source edit,
  rollback feasibility and preserved data/availability across the transition.
- **Evidence collection and reduction:** real, time-indexed packet/metric artifacts
  include irrelevant nodes and ambiguous symptoms. A reusable collector/parser
  can reduce mistakes and context volume. Score causal evidence coverage, sensitive
  data handling, safe collection scope and the cost of obtaining decisive evidence.
- **Version-sensitive migration:** a workload can be technically running while
  violating an AKS support/ownership constraint. Evaluate supported eligibility,
  an executable staged plan and justified blockers across unseen version/profile
  combinations, not recognition of a single error string.

Use the **same raw documents and executable capabilities** in the control. Compare
unstructured references with a curated procedure to test organization; compare
identical procedure bodies across help-only and native metadata exposure to test
discovery. Providing an exclusive secret answer or extra privileged tool only to
the skill arm would not isolate procedural benefit. Our print-only CLI catalog
does not yet measure the full benefit of installed skill packages with bundled
scripts and references.

A useful reporting decomposition is **exposure → selection → retrieval → correct
application → task outcome**. Each stage can fail independently. Long prose or an
overconfident one-path recipe can make a strong baseline worse; a supportable
blocked outcome should not be punished solely because no mutation was made.

## Predeclared consecutive-error experiment

New action: `aks_bench error-ladder`.

- Tasks: `manual-scale` (familiar operation control) and `egress-incident-snat`
  (multi-source investigation). Prior GPU trials inform the research but are not
  evidence about an error threshold on that task class.
- Model: explicitly requested local Copilot `gpt-6.1-sol`; record observed model.
- Conditions: no-skills baseline and **normal AKS-help-only** skill availability.
  Identical task prompt, fixture, catalog and public workspace within each pair.
  No startup skill metadata, no prompt hints, no contextual diagnostic references.
- Errors: synthetic ARM-style HTTP 503 with Retry-After 1 second, or a synthetic
  Azure CLI exception before modeled API dispatch. Neither error text mentions
  skills, runbooks, discovery commands or help. Both exit 1.
- Budgets: first **0, 1, 2, 3, 5 or 8 eligible Azure invocations** fail, then normal
  dispatch resumes; **-1** is persistent failure. Thus two failures permit recovery
  on eligible call 3, three on call 4, five on call 6, eight on call 9.
- One budget is shared across Azure command families and flag spellings in each
  trial. Switching from show to list consumes the same prefix budget. This is a
  synthetic service/CLI availability experiment, not a claim all Azure APIs share
  a physical outage. Counts are invocations observed by the agent, **not real ARM
  HTTP retries inside the SDK**, and not necessarily separate model decisions.
- Help, skill calls, account/version/configuration commands and kubectl/docs are
  not faulted and do not consume the budget. The intent is to keep local help
  reachable. Thus a failure streak among eligible Azure calls can have successful
  local/Kubernetes reads in between; it is not a streak across every shell command.
- Finite/persistent budgets are hidden from the agent. There is no implicit promise
  in the task prompt that retrying a certain number of times will recover.
- First pass: seed 71, one matched pair per task/error/budget cell: **56 trials**.
  Cell and arm order are seeded/shuffled. 180-second wall limit, fresh isolated
  containers and default modeled latency. This is an exploratory threshold study,
  not a precise probability estimate or a universal model threshold.

### Recorded outcomes

Each trace records fault kind, eligible attempt, injection versus normal dispatch,
exit/status, timestamps and unchanged state on rejected calls. ARM errors cost one
modeled request; client-side exceptions cost zero modeled API requests. Original
task scoring is unchanged. Planned errors are not simulator coverage gaps; missing
command coverage still invalidates a trial and is retained.

Results separately record the first successful AKS help, first skill seek
(list/search/show or bare skill group), and first successful skill content read,
with prior injected-error count and whether recovery was already observed. A seek
is not a read, and a read after recovery is not pre-recovery fallback. No read is
reported as **not observed before trial end**, never as a made-up threshold.
Report failures actually observed, not just failures configured: an agent may stop
before it reaches the scheduled recovery call. Shell retry loops can generate many
errors without a model round trip; do not treat each as a new decision to reject skills.

### Run

```sh
PYTHONPATH=bench .venv-bench/bin/python -m aks_bench error-ladder \
  --bwrap /tmp/opencode/bubblewrap/usr/bin/bwrap \
  --copilot /home/david/.local/bin/copilot --model gpt-6.1-sol \
  --seed 71 --timeout 180 --output benchmark-results/error-ladder-sol-20261116
```

Use `--failure-counts 2 3` for recovery on calls three/four, `--failure-counts -1`
for persistent failure, or `--failure-kinds arm503` for just ARM-style failures.
`--repeats` uses fresh seeded sessions. Other supported model IDs and Foundry remain
available; do not combine different models into a single inferred threshold.

Live results will be added after the frozen run and trace review.
