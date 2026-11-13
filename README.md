# az-aks-skills-cli

Prototype a new Azure CLI command group that lets humans and agents retrieve
AKS skills directly from their CLI:

```sh
az aks skill list
az aks skill search "upgrade"
az aks skill show --name aks-upgrade
```

An executable `bin/az` owns the exact `az aks skill` prefix and its `az aks skills`
alias. AKS help pages include local discovery entries; other invocations are
handed to the installed Azure CLI. Skills are Markdown instructions;
the commands print them without executing their contents.

## Try it

Requires Python 3.10+. Azure CLI is required only for forwarded commands.
From either checkout:

```sh
./bin/az aks skill list
./bin/az aks skill search "node capacity" -o json
./bin/az aks skill show --name aks-upgrade
./bin/az aks skill show --name aks-upgrade -o json
./bin/az aks skill --help
```

Running just `az aks skill` or `az aks skills` prints group help and exits
successfully. Help follows Azure CLI's `Group`/`Command`, `Commands`, `Arguments`,
`Global Arguments`, and `Examples` layout. Use `-h` or `--help` on the group or
any subcommand:

```sh
az aks skills
az aks skill search --help
az aks skill show --help
```

`skills` is an alias for the entire command group. Search takes positional text
(`search "upgrade"`); show takes `--name` (`show --name aks-upgrade`).

To make the shim the `az` command in your current Bash or Zsh session, run this
from the checkout **before adding its `bin` to PATH**:

```sh
export AZ_AKS_REAL_AZ="$(command -v az)"
export PATH="$PWD/bin:$PATH"
hash -r

az aks skill list          # local prototype
az aks list -o table       # real Azure CLI
az account show            # real Azure CLI
```

`AZ_AKS_REAL_AZ` must be an absolute executable path (on the initial development
machine it is `/usr/bin/az`). If your shell already has an `az` alias/function,
remove it or invoke `./bin/az` directly. Without this variable, the shim searches
PATH for another executable named `az`, skipping itself and previously visited
shim instances. No global installation or shell-profile edit is required. A fresh
terminal restores your normal PATH. To switch worktrees, prepend the new
checkout's `bin` while keeping `AZ_AKS_REAL_AZ` pointed at the real CLI.

## Interface

| Command | Default output | Other output |
| --- | --- | --- |
| `az aks skill list` | ID and description table | `-o json` |
| `az aks skill search "terms"` | Matching ID and description table | `-o json` |
| `az aks skill show --name ID` | Full Markdown document | `-o json` |

Search matches all whitespace-separated terms, case-insensitively, against the
ID, title, description, and tags. Results are ordered by ID. An empty result is a
successful response (`[]` in JSON); an unknown ID is an error. Each JSON summary
has `id`, `title`, `description`, and `tags`; `show` adds `content`.

This is a shim experiment, not an installed Azure CLI extension. `az aks --help`
lists `skill` and `skills` under Subgroups. Descendant help such as
`az aks create --help` includes a Related Commands entry for skill discovery,
while retaining the real Azure CLI help. `az --help` retains the normal entry
for AKS. The local skill commands do not implement Azure CLI globals such as
`--query`, `--debug`, or `--subscription` for local skill commands. Options must
follow the subcommand. See [the design](docs/design.md) for the discovery plan.

## Add skills

Add a Markdown file under `skills/<id>/SKILL.md` and an entry in
[`skills/index.json`](skills/index.json). The index uses this shape:

```json
{
  "version": 1,
  "skills": [
    {
      "id": "example",
      "title": "Example skill",
      "description": "When this skill is useful.",
      "tags": ["example"],
      "path": "example/SKILL.md"
    }
  ]
}
```

Use `AZ_AKS_SKILLS_DIR=/absolute/path/to/catalog` to select another directory
containing `index.json` and its Markdown files. The catalog is resolved relative
to the shim's checkout by default, so it works from any current directory.

## Development and worktrees

```text
/home/david/.worktrees/az-aks-skills-cli/
├── main/       # primary Git checkout, main branch
└── prototype/  # linked worktree, feat/skill-shim branch
```

Each worktree has its own source and bundled catalog; Git objects are shared.

```sh
python3 -m unittest discover -s tests -v
git worktree list

# Run from main/ to start another independent experiment:
git worktree add ../search-experiment -b feat/search-experiment
```

Tests use a fake Azure CLI and temporary catalogs; no Azure login or network is
needed. The included skills are small examples for exercising the interface.

## Isolated Copilot benchmark

[`docs/benchmark.md`](docs/benchmark.md) describes the runnable skills-vs-no-skills
experiment: stateful fake clusters, scripted success/errors across a captured
99-command AKS registry, 27 research-derived scenarios, rootless/Docker
containers, timestamped call traces, state-based scoring, and model/network metrics.

It uses your local Copilot CLI (`gpt-6.1-sol` by default), with model selection and
optional Azure AI Foundry BYOK. The mock never delegates to the real Azure CLI.
Run `check` to verify containment, `replay` to validate fixtures, then `run` for
actual paired agent trials. Full setup and interpretation guidance are in the
benchmark document.

The [initial Sol pilot results](docs/benchmark-pilot.md) include 10 guided-use
trials and four passive-discovery trials. All tasks succeeded, but guided skills
added overhead in this small pilot; passive availability produced no skill reads.
The [help-change rerun](docs/benchmark-help-evaluation.md) compares the updated
help interface. [Two AKS Automatic scenarios](docs/aks-automatic-scenarios.md)
cover managed cluster creation and separate Kubernetes/node-image maintenance windows.

Current runs use **discovery-only, identical prompts**, with no runbook hint.
[Troubleshooting scenarios](docs/troubleshooting-benchmark.md) add persistent
upgrade, Automatic registration and managed-namespace quota failures, plus logged
Microsoft Learn access for both arms. Use `--docs-mode off` for an offline comparison.
The [discovery-only troubleshooting pilot](docs/troubleshooting-pilot.md) records
valid matched pairs and the observed help-to-skill discovery path.

The [17-candidate evaluation](docs/candidate-evaluation.md) adds namespace lifecycle,
registry, identity, NAP, admission, PDB, CSI, networking and Gateway fixtures, with
16 additional skills. It records **78 live trials** including coverage reruns.
The latest audited pairs completed 16/17 baseline tasks and 17/17 skills-available
tasks, with **zero skill reads**—no demonstrated skill-content benefit.

## Task-focused skill design

The [skill coverage and tuning guide](docs/skill-catalog-tuning.md) explains the
original nine benchmark skills and the original-versus-revised content comparison.
The [discovery trace review](docs/skill-discovery-review.md) shows when the agent
encounters the help entry, chooses a skill, or proceeds without one.
The [observed task/action map](docs/task-action-skill-map.md) maps those reads to
specific workflows. The [FAQ/guide candidate map](docs/scenario-candidate-map.md)
maps the 17 additional tasks across eight topics, with a source index and
machine-readable scenario designs. Their primary fixtures are implemented;
held-out variants remain future work. The benchmark catalog now has 25 skills.
To inspect that catalog directly:

```sh
AZ_AKS_SKILLS_DIR="$PWD/bench/skills" ./bin/az aks skill list
```

The standalone catalog also includes new skills for **ACR image pulls**,
**workload identity**, and **PDB-blocked upgrades**. Their
[Microsoft Learn research and scenario designs](docs/typical-aks-task-designs.md)
specify success paths, failure branches, invariants and required simulator state.
Primary variants of all three workflows are now modeled in the candidate suite.
