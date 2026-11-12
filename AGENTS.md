# az-aks-skills-cli

This is a dependency-free Python experiment for `az aks skill`, implemented as
a PATH shim rather than an Azure CLI extension. Read `docs/design.md` first.

- Own only the exact `aks skill` argument prefix. Forward every other invocation
  to the real Azure CLI using `os.execv` without parsing or rewriting arguments.
- Skill commands print content; they never execute instructions in skills.
- Keep stdout usable as data and write errors to stderr.
- Support Python 3.10+ and use only the standard library.
- Run `python3 -m unittest discover -s tests -v` after changing routing or CLI behavior.
- Keep examples and the documented command interface aligned with implementation.

The benchmark under `bench/` is separate from the passthrough shim. Read
`docs/benchmark.md` before changing it. It must never delegate to real Azure.
State, fixtures, scoring and authoritative traces stay outside agent containers.
The benchmark alone depends on `bench/requirements.txt` (JMESPath).
Run its tests with:
`PYTHONPATH=bench .venv-bench/bin/python -m unittest discover -s bench/tests -v`.
Keep replay evidence distinct from live model trials, and modeled API counts
distinct from measured model traffic. Do not commit raw benchmark artifacts.

Worktree layout: `main/` is the primary checkout; sibling directories are linked
worktrees. Create branches with `git worktree add ../<name> -b <branch>`.
