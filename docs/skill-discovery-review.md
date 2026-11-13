# How the agent discovers and chooses CLI skills

## Main finding

In the recorded hint-free sessions that used skills, the first observable entry
point was **Azure CLI help output**, primarily the Related Commands footer of
`az aks create --help`. There were no recorded Unix man-page lookups.

Help exposure is much more frequent than skill use. The agent often receives the
entry and proceeds with the ordinary workflow without opening a skill.

## Latest controlled catalog study

The latest study has 20 skill-enabled runs: original and revised catalogs across
five scenarios and two seeds. All 20 were valid, and their prompts did not mention
skills. The ten no-skills controls are outside the exposure/adoption table below.

| Scenario | Skill-enabled runs | Received help advertising skills | Read a skill |
|---|---:|---:|---:|
| Fixed-size node pool | 4 | 0 | 0 |
| Automatic creation | 4 | 4 | 0 |
| Automatic maintenance | 4 | 4 | 0 |
| Provider-registration recovery | 4 | 4 | 3 |
| Managed-namespace quota recovery | 4 | 4 | 0 |
| **Total** | **20** | **16** | **3** |

The 16 exposures were verified in completed tool-result content, not inferred
merely because the mock implements an overlay. In all three using runs, that
content was delivered **before the agent requested its first skill command**.
This avoids counting help and skill commands preplanned in the same shell call
as proof of discovery from that help.

Thus, 13 runs received an entry and ignored it, while four scaling runs did not
request help and never encountered the entry. Three of four provider-recovery
runs used skills, but two seeds per catalog are too few to establish an adoption
rate for that task or for Sol generally.

## Exact observed route

For `catalog-tuning-20261113/debug-automatic-provider-2-revised`, the sequence was:

```text
 8.73s  az aks create --help
12.54s  az aks skill --help
14.68s  az aks skill search automatic
16.82s  az aks skill show --name aks-automatic-create
16.90s  az aks skill show --name aks-debug-provider
```

The creation help returned this entry:

```text
Related Commands
    az aks skill : Find and print AKS skills and troubleshooting instructions.
        Run 'az aks skill' to list its commands and examples.
```

The first entry introduces the group; `az aks skill --help` then teaches its
subcommands. List/search exposes skill IDs; show retrieves the actual procedure.
The agent used the singular spelling, despite the available plural alias.

Local evidence anchors in that trial's `copilot.stdout.jsonl`:

- Line 178: completed creation-help tool result containing the footer above.
- Line 309: subsequent request for `az aks skill --help`.
- Line 473: request to read both creation and provider-recovery skills.

The times are host-observed CLI starts relative to container launch. The ordering
is also confirmed by Copilot tool-request/completion timestamps.

## When it chooses the skills

The observed association is with **provider-creation recovery**, not with every
failure or every task involving Automatic. Successful creation and maintenance
also showed the same generic help entry but produced zero reads in this study.
Quota recovery was a troubleshooting task and also produced zero reads.

In all three latest-study readers, provider registration had **already succeeded
before the first full skill document was opened**:

| Trial | Registration completed | First document read |
|---|---:|---:|
| Provider seed 1, original | 14.84s | 19.16s |
| Provider seed 2, original | 16.50s | 18.68s |
| Provider seed 2, revised | 12.62s | 16.82s |

The tool sequence is consistent with consulting guidance for the remaining
creation/verification steps, after diagnosing and performing the registration
repair. We cannot infer the model's internal motivation from these traces.

The lookup is also broad: two runs used list and one searched `automatic`, rather
than searching the exact registration error code. All three read the creation
and provider-recovery documents.

## Why making a document self-contained did not eliminate the second read

Both seed-2 runs requested the two documents together:

```sh
az aks skill show --name aks-automatic-create &&
az aks skill show --name aks-debug-provider
```

The seed-1 original run issued the two show requests concurrently. In each case,
the agent had selected both documents **before reading either body**. A sentence
inside the first document saying the recipe is complete cannot prevent a second
fetch that is already queued. This is a selection-stage issue, not just a body
length issue.

## Broader retained history

The audit examined 94 retained live session outputs across multiple revisions,
including earlier explicitly hinted runs. No recorded shell command invoked
`man`/`apropos` or looked under `/usr/share/man`. No no-skills control attempted
the custom skill command.

Across the seven hint-free sessions that called skills:

- Six had a prior `az aks create --help` result advertising the skill group.
- One earlier version-skew session had a preceding help bundle containing
  `az aks --help`, `az aks nodepool --help`, and upgrade command help. That bundle
  exposed both the parent Subgroups entry and descendant Related Commands entries;
  the trace cannot establish which individual entry prompted the choice.
- All seven used shell tools; there was no web/documentation fetch or native file
  tool acting as the source of the skill command in those sessions.
- Two of those seven had simulator coverage gaps. Their sequences are evidence
  of discovery capability, but their performance remains excluded.

These are repeated development experiments with changing configurations, not a
single statistical sample. Earlier guided runs explicitly named the commands in
the prompt and do not count as evidence of independent discovery.

## Interpretation

1. **The working entry point is command-specific CLI help**, especially the
   creation-help footer; it is not a Unix man page.
2. **Visibility does not ensure selection.** Most exposed runs ignored the entry.
3. **Selection is often late.** In the latest readers, a key repair step was
   already complete before document retrieval.
4. **Prefetch selection matters.** The agent selected two overlapping documents
   before seeing either one's self-contained procedure.

These observations support testing more task-specific help/search entries and
single-recipe selection in a separate experiment. They do not establish that
changing help text or document content will necessarily improve adoption or time.

Raw evidence stays local and gitignored. The audit summary is at
`benchmark-results/skill-discovery-review/audit.json`; the primary study is
`benchmark-results/catalog-tuning-20261113/`. The public report contains only
aggregate findings and relevant command/help excerpts.
