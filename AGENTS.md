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

Worktree layout: `main/` is the primary checkout; sibling directories are linked
worktrees. Create branches with `git worktree add ../<name> -b <branch>`.
