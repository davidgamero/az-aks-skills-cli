"""The deliberately small local command surface."""

import argparse
import json
import sys
import textwrap

from .catalog import Catalog, CatalogError, summary


class AzArgumentParser(argparse.ArgumentParser):
    """Azure-style help sections while retaining argparse validation."""

    def __init__(self, *args, examples=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.examples = examples

    def format_help(self) -> str:
        subcommands = next((action for action in self._actions
                            if isinstance(action, argparse._SubParsersAction)), None)
        lines = ["Group" if subcommands else "Command",
                 f"    {self.prog} : {self.description}", ""]

        def section(title, rows):
            if not rows:
                return
            lines.append(title)
            width = max(len(label) for label, _ in rows)
            for label, description in rows:
                prefix = f"    {label:<{width}} : "
                lines.extend(textwrap.wrap(description, width=100, initial_indent=prefix,
                                           subsequent_indent=" " * len(prefix)))
            lines.append("")

        if subcommands:
            section("Commands:", [(name, command.description)
                                  for name, command in subcommands.choices.items()])
        arguments, globals_ = [], []
        for action in self._actions:
            if isinstance(action, argparse._SubParsersAction):
                continue
            label = " ".join(sorted(action.option_strings, key=len, reverse=True)) or action.dest.upper()
            if action.required:
                label += " [Required]"
            description = action.help or ""
            if action.dest == "help":
                description = "Show this help message and exit."
            if action.choices:
                description += f" Allowed values: {', '.join(action.choices)}."
            if action.default not in (None, argparse.SUPPRESS):
                description += f" Default: {action.default}."
            rows = globals_ if action.dest in ("help", "output") else arguments
            rows.append((label, description))
        section("Arguments", arguments)
        section("Global Arguments", globals_)
        if self.examples:
            lines.append("Examples")
            for description, command in self.examples:
                lines.extend([f"    {description}", f"        {command}", ""])
        return "\n".join(lines) + "\n"


def parser(prog: str = "az aks skill") -> argparse.ArgumentParser:
    result = AzArgumentParser(
        prog=prog, description="Find and print AKS skills from a local catalog.",
        allow_abbrev=False,
        examples=(
            ("List available skills.", f"{prog} list"),
            ("Search skill metadata using a positional search string.", f'{prog} search "upgrade"'),
            ("Print a skill's instructions.", f"{prog} show --name aks-upgrade"),
        ),
    )
    commands = result.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", description="List available skills.", allow_abbrev=False,
                                  examples=(("List skills as JSON.", f"{prog} list --output json"),))
    searching = commands.add_parser("search", description="Search skill metadata.", allow_abbrev=False,
                                    examples=(("Find upgrade skills.", f'{prog} search "upgrade"'),
                                              ("Search multiple terms and return JSON.", f'{prog} search "node capacity" -o json')))
    searching.add_argument("query", help="Positional search text. Matches all terms, case-insensitively. Do not use --query.")
    showing = commands.add_parser("show", description="Print a skill's instructions.", allow_abbrev=False,
                                  examples=(("Print the upgrade skill as Markdown.", f"{prog} show --name aks-upgrade"),
                                            ("Return skill metadata and content as JSON.", f"{prog} show --name aks-upgrade -o json")))
    showing.add_argument("--name", required=True, help="Exact skill ID from list or search.")
    for command in (listing, searching):
        command.add_argument("--output", "-o", choices=("table", "json"), default="table", help="Output format.")
    showing.add_argument("--output", "-o", choices=("markdown", "json"), default="markdown", help="Output format.")
    return result


def run(args: list[str], prog: str = "az aks skill") -> int:
    command_parser = parser(prog)
    if not args:
        command_parser.print_help()
        return 0
    options = command_parser.parse_args(args)
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
