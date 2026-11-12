"""The deliberately small local command surface."""

import argparse
import json
import sys

from .catalog import Catalog, CatalogError, summary


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="az aks skill", description="Find and print AKS skills from a local catalog.",
        allow_abbrev=False,
    )
    commands = result.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="List available skills", allow_abbrev=False)
    searching = commands.add_parser("search", help="Search skill metadata", allow_abbrev=False)
    searching.add_argument("query", help="Case-insensitive terms; all terms must match")
    showing = commands.add_parser("show", help="Print a skill's instructions", allow_abbrev=False)
    showing.add_argument("--name", required=True, help="Exact skill ID")
    for command in (listing, searching):
        command.add_argument("--output", "-o", choices=("table", "json"), default="table")
    showing.add_argument("--output", "-o", choices=("markdown", "json"), default="markdown")
    return result


def run(args: list[str]) -> int:
    options = parser().parse_args(args)
    try:
        catalog = Catalog()
        if options.command == "show":
            skill = catalog.get(options.name)
            content = catalog.content(skill)
            if options.output == "json":
                print(json.dumps({**summary(skill), "content": content}, indent=2))
            else:
                sys.stdout.write(content)
            return 0
        skills = catalog.skills if options.command == "list" else catalog.search(options.query)
        rows = [summary(skill) for skill in skills]
        if options.output == "json":
            print(json.dumps(rows, indent=2))
        elif rows:
            width = max(len("NAME"), *(len(row["id"]) for row in rows))
            print(f"{'NAME':<{width}}  DESCRIPTION")
            for row in rows:
                print(f"{row['id']:<{width}}  {row['description']}")
        else:
            print("No skills found.")
        return 0
    except CatalogError as error:
        print(f"az aks skill: {error}", file=sys.stderr)
        return 1
