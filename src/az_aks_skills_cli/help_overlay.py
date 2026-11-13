"""Add local discovery entries to Azure CLI help without changing its commands."""

import re

SKILL_DESCRIPTION = "Find and print AKS skills and troubleshooting instructions."


def patch_aks_help(text: str, command: str = "aks") -> str:
    if command != "aks":
        if "az aks skill :" in text:
            return text
        return text.rstrip() + ("\n\nRelated Commands\n"
                                f"    az aks skill : {SKILL_DESCRIPTION}\n"
                                "        Run 'az aks skill' to list its commands and examples.\n")
    lines = text.splitlines(keepends=True)
    entries = [("skill", SKILL_DESCRIPTION), ("skills", "Alias for 'az aks skill'.")]
    start = next((i for i, line in enumerate(lines) if line.strip() == "Subgroups:"), None)
    if start is None:
        start = next((i for i, line in enumerate(lines) if line.strip() == "Commands:"), len(lines))
        if start and lines[start - 1].strip():
            lines.insert(start, "\n")
            start += 1
        lines[start:start] = ["Subgroups:\n", "\n"]
    end = start + 1
    while end < len(lines) and lines[end].strip():
        end += 1
    existing = {match.group(1) for line in lines[start + 1:end]
                if (match := re.match(r"^\s+(\S+)\s+(?:\[.*?\]\s*)?:", line))}
    widths = [line.index(":") - 5 for line in lines[start + 1:end] if ":" in line]
    width = max([6, *widths])
    insert = [f"    {name:<{width}} : {description}\n" for name, description in entries if name not in existing]
    lines[end:end] = insert
    return "".join(lines)
