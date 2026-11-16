# Skill usefulness, discoverability and consecutive-error fallback

## Result

**Repeated errors did not cause observable skill fallback in this experiment.**
We ran **84 live Copilot trials** with requested and observed model `gpt-6.1-sol`.
After auditing command coverage and failure schedules, **75 trials are valid**,
including **36 with skills available through ordinary AKS help**. There were:

- **0 skill searches, lists, bare-group requests or content reads** in all 84
  trials, including invalid runs. An audit of model-requested tools also found no
  skill-related file searches/reads outside the CLI.
- **One valid skill-enabled trial** that requested AKS help. It did so after two
  injected CLI exceptions, received the skill entry in completed tool results,
  and ignored it. It recovered on eligible Azure call four.
- **Up to eight consecutive injected failures in valid trials**, without skill
  retrieval. Larger configured budgets did not guarantee more observed errors:
  agents often stopped before reaching the scheduled recovery call.

There is **no observed error-count threshold for skill retrieval**. This does not
mean the threshold is nine, or that a model would never retrieve a skill. It means
retrieval was not observed within these tasks, error types, sessions and budgets.
Help requests are not the same as skill requests, and we cannot infer internal
motivation from tool traces.

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

## Live results and audit

### Runs

| Batch | Frozen revision | Seed | Scope | Live trials | Audited valid | Invalid |
|---|---|---:|---|---:|---:|---:|
| Initial matrix | `22ae2b3` | 71 | Both tasks, both error types, seven budgets, two conditions | 56 | 48 | 8 |
| Corrected operation matrix | `d09310d` | 72 | Manual scale, both error types, seven budgets, two conditions | 28 | 27 | 1 |
| **Total** | | | | **84** | **75** | **9** |

Seven trials had existing simulator command-coverage gaps: multivalue Azure metric
aggregation syntax, a diagnostic shell bundle containing `date`, or direct ARM
REST pool reads not implemented in the earlier operation simulator. They remain
invalid even when the agent later completed its task.

The audit additionally found **two initial manual-scale trials** where a boolean
autoscaler flag escaped the failure gate. That classifier used a parser which
expected a value for the flag; the write succeeded while other commands failed.
Those eight-failure/persistent CLI-error treatment trials are invalid even though
the original machine results called them valid. The 13-error maximum reported
during the first inspection came from one of these invalid schedules; **the valid
maximum is eight**, not 13. Their observations are retained but are not clean
consecutive-error evidence.

Revision `d09310d` classifies the command prefix independently of option-value
parsing. A new regression test ensures boolean write flags cannot bypass the gate.
The entire 28-trial operation matrix was rerun on seed 72, including failures,
rather than selectively rerunning cells until they pass. Only one rerun was
invalid, for the unimplemented REST fallback; it was not silently counted as an
agent failure or success in comparisons.

The separate audit at `7e6421d` checks recorded injection against the intended
schedule, unchanged state on rejected calls, absence of contextual references and
visible tool requests. It changes **validity only** for schedule violations. It
does not rerun inference, change task scoring, rewrite original artifacts or
replace failures with later successes. Initial and rerun results are reported as
separate batches, not paired across seeds/revisions.

### Discovery across audited valid trials

| Measure | No skills | Help-discoverable skills |
|---|---:|---:|
| Live trials retained | 42 | 42 |
| Audited valid trials | 39 | 36 |
| Trials opening AKS help | 2 | 1 |
| Trials requesting skill commands | 0 | 0 |
| Trials reading a skill | 0 | 0 |
| Contextual diagnostic hints | 0 | 0 |
| Documentation fetch attempts | 0 | 0 |

There were no timeouts. All 84 containers passed their isolation checks. All
observed model names were `gpt-6.1-sol`; local Copilot CLI was 1.0.98. Within each
scenario/seed/run, the prompts and complete serialized fixtures were byte-identical
across conditions and failure budgets. Failure configuration stayed outside the
agent's public context. The catalog was unchanged from the investigation study.

### After how many errors did help or skills appear?

Each row counts only valid skill-enabled trials from the two batches. The number
of trials varies because the second batch repeats only the operation task and
invalid cells remain excluded. These counts are descriptive, not a population
adoption probability or independent repetitions of one identical task.

| Configured initial failures | First normally dispatched eligible call | Valid skill-enabled trials | Injected failures actually observed | Trials opening AKS help | Skill seeks / reads |
|---|---:|---:|---|---:|---:|
| 0 | 1 | 6 | 0 | 0 | 0 / 0 |
| 1 | 2 | 4 | 1 | 0 | 0 / 0 |
| 2 | 3 | 5 | 2 | 0 | 0 / 0 |
| 3 | 4 | 6 | 3 | 1, after error 2 | 0 / 0 |
| 5 | 6 | 5 | 5 | 0 | 0 / 0 |
| 8 | 9 | 5 | 6–7 | 0 | 0 / 0 |
| Persistent | Never | 5 | 5–8 | 0 | 0 / 0 |

In the configured-eight treatment trials that remained valid, the agent did not
reach recovery call nine. The persistent CLI-error treatment on seed 72 observed
eight failures and stopped with a blocked report. In the first batch, a baseline
also requested help after two CLI errors under persistent failure, but had no
skill entry available. In the corrected batch another baseline opened help after
two errors and recovered on call three. **Two errors sometimes preceded help; they
did not establish a help or skill-use threshold.**

### Corrected manual-scale matrix: seed 72

**B/H = no skills / help-discoverable skills.** “Blocked” means the requested state
was not achieved/verified, not that stopping was necessarily an operational error.
Calls are permitted to dispatch normally after the budget; a subsequent argument
or coverage error can still fail, so permission to recover is not guaranteed task
completion. Task outcome and discovery outcome are separate.

| Fail first | Recovery permitted on call | ARM-style outcome B/H | ARM errors observed B/H | CLI-exception outcome B/H | CLI errors observed B/H |
|---|---:|---|---|---|---|
| 0 | 1 | Pass / Pass | 0 / 0 | Pass / Pass | 0 / 0 |
| 1 | 2 | Pass / Pass | 1 / 1 | Pass / Pass | 1 / 1 |
| 2 | 3 | Pass / Pass | 2 / 2 | Pass / Pass | 2 / 2 |
| 3 | 4 | Pass / Pass | 3 / 3 | Pass / Pass | 3 / 3 |
| 5 | 6 | Pass / Blocked | 5 / 5 | Pass / Invalid coverage | 5 / 5 |
| 8 | 9 | Blocked / Blocked | 6 / 6 | Blocked / Blocked | 8 / 7 |
| Persistent | Never | Blocked / Blocked | 7 / 5 | Blocked / Blocked | 7 / 8 |

Every cell had zero skill requests. The five-error ARM treatment stopped at the
last injected error without sending the next permitted call. Some other trials
tried alternative command spellings or direct REST rather than continuing the
same operation. These behaviors make “retry number” ambiguous without specifying
the shared eligible-call budget; the experiment logs exact argv and command families.

### Exact observed help route, without skill retrieval

`manual-scale-72-cli_error-f3-help`:

```text
 5.93s  Azure call 1: nodepool list → CLI exception
 7.78s  Azure call 2: nodepool show → CLI exception
 9.95s  account show → success (local fixture, outside gate)
 9.98s  az --version → success
12.71s  az aks nodepool --help → success, skill entry advertised
17.55s  Azure call 3: aks show → CLI exception
17.56s  nodepool update --help and scale --help → success, skill entries advertised
20.79s  Azure call 4: disable autoscaler → success
22.93s  Azure call 5: scale pool → success
25.31s  Azure call 6: verify pools → success
```

The completed model-visible tool results contain the normal Related Commands
footer **before later model requests**. This is actual delivered exposure, not
merely the existence of an overlay or a preplanned help-and-skill shell command.
The agent never requested list/search/show or searched local skill files.

### Investigation failures are not all bad reasoning

In the seed-71 networking runs, several reports after recovered service calls
identified SNAT pressure but failed the existing exact-citation/evidence rubric.
Their original scores are retained; they are not evidence that the diagnosis was
wrong, nor evidence of skill benefit. No content was retrieved in either condition.

When historical ARM metrics never became available, an agent wrote an unconfirmed
report: connection establishment was failing, DNS evidence looked healthy, and
SNAT remained plausible but unproven without incident usage/allocation/failure
metrics. It recommended collecting those metrics rather than changing the cluster.
That is an appropriate epistemic boundary even though the task's confirmed-diagnosis
oracle does not pass. A skill cannot truthfully replace unavailable evidence.

## Interpretation and next decisions

1. **Do not rely on repeated failures as a discovery mechanism.** More failures
   mostly produced retries, alternate commands, environment/version checks, direct
   REST attempts, or a blocked report—not catalog exploration.
2. **Discovery still depends on prior visibility.** Only one of 36 valid
   skill-enabled trials encountered AKS help. That one ignored the entry. Native
   installed-skill metadata, a catalog entry in a tool schema, and contextual
   references are distinct interfaces and need their own controls.
3. **A content test needs a real procedural gap.** The current frontier-model
   baselines often know the task. Prioritize organization-specific recovery,
   validated evidence tooling and version/ownership-dependent workflows. Keep raw
   evidence and capabilities available to both arms, then evaluate held-out cases.
4. **No universal retry threshold was found.** We tested one model/harness, two
   tasks and a limited seed frame. It would be unjustified to say “the model uses
   skills after N failures” or “the threshold is greater than eight.” It may stop,
   never consider this unadvertised catalog, or behave differently in another host.
5. **Do not manufacture usefulness by injecting more outages.** For pure availability
   failures, a correct bounded retry/circuit-breaker policy is a better success
   criterion than mandatory skill use. If testing discovery, measure exposure,
   seeking and retrieval independently of task repair.

Compared with the earlier explicit contextual-reference experiment (4/7 reads),
these no-error-hint trials show no spontaneous retrieval. Those were different
tasks/seeds and development studies; this is not a matched causal effect estimate
of adding a hint to an error. This study intentionally did **not** put hints there.

## Reproducibility

| Artifact | Revision | Local directory |
|---|---|---|
| Initial 56 live trials | `22ae2b3` | `benchmark-results/error-ladder-sol-20261116` |
| Corrected 28 operation trials | `d09310d` | `benchmark-results/error-ladder-sol-corrected-20261116` |
| Separate 84-trial schedule/tool audit | `7e6421d` | `benchmark-results/error-ladder-audit-20261116` |
| Eight isolated transport checks, no inference | `22ae2b3` working build | `benchmark-results/error-ladder-transport-20261116` |

Both live batches recorded clean working trees at launch. Source SHA-256 values:

- Initial: `255a9f0e91474b94934978fccc711b75af6b0b9b5959aff69b406b06faca8b11`.
- Corrected: `f25bdbc268b50acbad752b5d22ca8e210b17c98c053ef98eb4a5d768ad0c4139`.
- Catalog, both runs: `5f2ccb768507b99090421700194b933d1fc3ad8d5b10b9d4cccd036c52af3e19`.

Raw trial artifacts and source snapshots are gitignored. The audit can be reproduced
without model inference or rewriting original results:

```sh
PYTHONPATH=bench .venv-bench/bin/python bench/audit_error_ladder.py \
  --runs benchmark-results/error-ladder-sol-20261116 \
         benchmark-results/error-ladder-sol-corrected-20261116 \
  --output benchmark-results/NEW-error-ladder-audit
```

Validation: **96 benchmark tests**, **19 shim tests**, and eight isolated gate/help
transport checks. No actual Azure/Kubernetes resource operations were performed.
