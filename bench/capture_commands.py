"""Run with Azure CLI's Python to snapshot the core AKS command surface offline.

/opt/az/bin/python3 bench/capture_commands.py > bench/commands.json
This loads command definitions only: it never invokes a resource operation.
"""

import json
from azure.cli.core import get_default_cli
from azure.cli.command_modules.acs import COMMAND_LOADER_CLS
from azure.cli.core import __version__

loader = COMMAND_LOADER_CLS(get_default_cli())
commands = sorted(name for name in loader.load_command_table(["aks"]) if name.startswith("aks "))
print(json.dumps({
    "source": "azure-cli core acs command module (extensions excluded)",
    "azure_cli_version": __version__,
    "commands": commands,
}, indent=2))
