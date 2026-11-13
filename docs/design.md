# Design: `az aks skill` through a PATH shim

## Goal

Test whether an Azure-CLI-shaped interface is useful for discovering and reading
AKS skills. Provide `show`, `list`, and `search`, while keeping normal Azure CLI
commands usable in the same shell. Start with a local catalog and a small,
dependency-free implementation that is easy to vary across Git worktrees.

## Architecture

```text
shell / agent
    |
    v
checkout/bin/az (first on PATH)
    |
    +-- argv starts with ["aks", "skill"] or ["aks", "skills"]
    |       -> local argument parser
    |       -> catalog metadata / Markdown
    |       -> stdout
    |
    +-- all other argv
            -> resolve real az
            -> os.execv(real_az, [real_az, *original_args])
```

The routing decision happens before argument parsing. Unknown local subcommands
fail locally, while `az aks show`, `az account show`, bare `az`,
and normal Azure CLI help all reach the real CLI. Quoted values and flags are
preserved as individual arguments: no shell command is reconstructed.

Delegation uses process replacement instead of a subprocess relay. The real CLI
inherits stdin/stdout/stderr, working directory, terminal, and environment
(including Azure configuration). It receives signals directly and supplies its
own exit status. The only added environment value is the internal
`_AZ_AKS_SKILL_SHIMS` path list used to prevent recursion across stacked shims.

## Real Azure CLI resolution

1. If `AZ_AKS_REAL_AZ` is set, require an absolute executable file. A bad override
   is an error rather than a silent fallback.
2. Otherwise walk PATH, skipping this executable, its symlinks/hard links, and
   previously visited shim paths.
3. If no executable is available, report a diagnostic on stderr and exit 127.

Pinning the real executable before activation is recommended for repeatable
experiments. There is no dependency on importing Azure CLI Python internals, its
Python environment, or extension registration. The initial target is Linux/macOS
with an executable shim on PATH; Windows launcher support is a future task.

## Command and output contract

- `list [-o table|json]`: all catalog summaries, sorted by ID.
- `search QUERY [-o table|json]`: all terms must occur in the combined metadata;
  case-insensitive substring matching, sorted by ID. No remote search or ranking.
- `show --name ID [-o markdown|json]`: exact ID lookup; prints the original
  Markdown or a summary object with an additional `content` string.
- `skills` is an alias for `skill`, including all commands and help.
- A bare `az aks skill` or `az aks skills` prints group help to stdout and exits 0.
- `-h`/`--help` is available for the group and each subcommand. Help uses Azure
  CLI-style Group/Command, Commands, Arguments, Global Arguments, and Examples
  sections, with required argument markers and explicit search/show syntax.
- Success and empty search: 0. Catalog/lookup failure: 1. Argument error: 2.
  Forwarding failure: 127. Forwarded commands retain their actual exit status.
- Normal output goes to stdout; error diagnostics go to stderr.

Use a positional search string to avoid repurposing Azure CLI's existing
`--query` name, which means JMESPath filtering. Local commands intentionally
implement only the documented output formats, rather than approximating the
full Azure CLI global-option machinery.

## Catalog

`index.json` is the authoritative metadata source and contains `version: 1` plus
a `skills` array. Every entry has a unique ID, title, description, string tags,
and a relative document path. Documents live in separate Markdown files; no YAML
parser or package dependency is needed. A future adapter can generate the index
from an existing skill collection.

The whole index is validated on load. Document paths must resolve inside the
catalog, including through symlinks, and must refer to existing files. `show`
reads UTF-8 content; listing/search operate only on metadata. Paths are not
exposed in JSON summaries. `AZ_AKS_SKILLS_DIR` selects a complete alternate
catalog, which makes agent experiments and temporary fixtures straightforward.

## Worktree setup

Keep the primary clone at `main/`, with linked worktrees as siblings. This follows
the existing directory convention and keeps the repository self-contained here.
The shim locates source and the default catalog using its resolved file location,
not the caller's current directory. Selecting a worktree's `bin` selects that
worktree's implementation and bundled content together.

## Discovery tradeoff and next experiments

Exact passthrough means the prototype is absent from the real CLI's parent help.
Users or agents can access `az aks skill --help` once they know the command. This
first version measures command usefulness and retrieval, not spontaneous
discovery through Azure CLI help.

Suggested follow-up experiments:

1. **Help discovery:** try an opt-in overlay for the exact `az --help` and
   `az aks --help` routes, preserving the real help output and adding a clearly
   labeled experimental group. Compare with a real extension integration.
2. **Agent retrieval:** supply a temporary catalog with fresh content and record
   actual shim invocations, then verify the answer uses the retrieved skill.
3. **Search quality:** compare metadata matching with Markdown full-text search
   and ranked results using a larger realistic catalog.
4. **Azure CLI integration:** implement an extension command group with the same
   output schema if the interface proves useful. Verify namespace support and
   native output/help behavior against the target Azure CLI version.

Keep logging opt-in if added, write it separately from stdout, and avoid collecting
the arguments or output of unrelated Azure CLI commands.

## Verification

Black-box tests invoke the executable shim. They check printed Markdown and JSON,
search behavior, error channels, catalog validation, and handling from another
working directory. A fake real CLI verifies argument boundaries, inherited input
and environment, working directory, exit status, and passthrough of lookalike
commands. PATH tests cover symlinks, missing executables, invalid overrides, and
stacked worktree shims. No live Azure operations are required.
