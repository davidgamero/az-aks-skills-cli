"""Route one command group locally and delegate everything else verbatim."""

import os
from pathlib import Path
import sys

from .cli import run


def find_real_az(shim_path: Path) -> Path:
    """Honor an explicit executable, otherwise search PATH past this shim."""
    explicit = os.environ.get("AZ_AKS_REAL_AZ")
    if explicit:
        candidate = Path(explicit)
        if not candidate.is_absolute():
            raise ValueError("AZ_AKS_REAL_AZ must be an absolute executable path")
        candidates = [candidate]
    else:
        candidates = [Path(entry or ".") / "az" for entry in os.get_exec_path()]

    # Track shim instances across execs so stacking worktree shims cannot loop.
    visited = set(os.environ.get("_AZ_AKS_SKILL_SHIMS", "").split(os.pathsep))
    visited.add(str(shim_path.resolve()))
    for candidate in candidates:
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            continue
        resolved = candidate.resolve()
        if str(resolved) in visited or os.path.samefile(resolved, shim_path):
            continue
        return resolved
    raise ValueError(
        "cannot find the real Azure CLI; set AZ_AKS_REAL_AZ to its absolute path"
    )


def main(shim_path: Path) -> int:
    args = sys.argv[1:]
    if args[:2] == ["aks", "skill"]:
        return run(args[2:])
    try:
        real_az = find_real_az(shim_path)
        visited = os.environ.get("_AZ_AKS_SKILL_SHIMS", "")
        os.environ["_AZ_AKS_SKILL_SHIMS"] = os.pathsep.join(
            part for part in (visited, str(shim_path)) if part
        )
        os.execv(str(real_az), [str(real_az), *args])
    except (OSError, ValueError) as error:
        print(f"az shim: {error}", file=sys.stderr)
        return 127
