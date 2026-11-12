# az-aks-skills-cli

Prototype a new Azure CLI command group that lets humans and agents retrieve
AKS skills directly from their CLI:

```sh
az aks skill list
az aks skill search "upgrade"
az aks skill show --name aks-upgrade
```

An executable `bin/az` owns **only** the exact `az aks skill` prefix. Every other
invocation is handed to the installed Azure CLI. Skills are Markdown instructions;
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

This is a shim experiment, not an installed Azure CLI extension. The initial
prototype does not advertise itself in `az --help` or `az aks --help`; those
commands are forwarded verbatim. It does not implement Azure CLI globals such as
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
