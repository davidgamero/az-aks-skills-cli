"""Deterministic fake ARM state, command fixtures, fault injection and audit log."""

import copy
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import threading
import time

import jmespath

from .scenarios import grade
from . import automatic
from . import troubleshooting, documentation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / "src"))
from az_aks_skills_cli.help_overlay import patch_aks_help
COMMANDS = json.loads((ROOT / "commands.json").read_text())["commands"]
SEMANTIC = {
    "aks list", "aks show", "aks create", "aks delete", "aks scale", "aks update",
    "aks start", "aks stop", "aks get-upgrades", "aks get-versions", "aks upgrade", "aks wait",
    "aks nodepool list", "aks nodepool show", "aks nodepool add", "aks nodepool delete",
    "aks nodepool scale", "aks nodepool update", "aks nodepool upgrade", "aks nodepool get-upgrades",
    "aks nodepool start", "aks nodepool stop", "aks nodepool wait",
    "aks maintenanceconfiguration add", "aks maintenanceconfiguration update",
    "aks maintenanceconfiguration delete", "aks maintenanceconfiguration list", "aks maintenanceconfiguration show",
    "aks namespace list", "aks namespace show", "aks namespace update",
}
AUXILIARY = {"group show", "group exists", "provider show", "provider list", "provider register"}
ALIASES = {"-g": "--resource-group", "-n": "--name", "-o": "--output", "-l": "--location", "-y": "--yes", "-h": "--help", "-k": "--kubernetes-version"}
FLAGS = {"--yes", "--help", "--version", "--debug", "--verbose", "--only-show-errors", "--no-wait",
         "--control-plane-only", "--enable-cluster-autoscaler", "--disable-cluster-autoscaler",
         "--update-cluster-autoscaler", "--generate-ssh-keys", "--updated", "--created", "--deleted", "--exists",
         "--enable-hosted-system", "--enable-managed-identity", "--wait"}
VALUES = {"--resource-group", "--name", "--cluster-name", "--nodepool-name", "--node-count", "--min-count",
          "--max-count", "--kubernetes-version", "--output", "--query", "--subscription", "--location",
          "--mode", "--node-vm-size", "--interval", "--timeout", "--custom", "--sku", "--tier",
          "--node-provisioning-mode", "--auto-upgrade-channel", "--node-os-upgrade-channel",
          "--network-plugin", "--network-plugin-mode", "--network-dataplane", "--network-policy", "--outbound-type",
          "--schedule-type", "--day-of-week", "--interval-weeks", "--duration", "--start-time", "--utc-offset",
          "--start-date", "--namespace", "--cpu-request", "--cpu-limit", "--memory-request", "--memory-limit",
          "--ingress-policy", "--egress-policy"}


class CLIError(Exception):
    def __init__(self, code, message, status=400, exit_code=1):
        super().__init__(message)
        self.code, self.status, self.exit_code = code, status, exit_code


def parse(argv):
    words, options = [], {}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg.startswith("-"):
            key, equal, value = arg.partition("=")
            key = ALIASES.get(key, key)
            if equal:
                options[key] = value
            elif key in FLAGS:
                options[key] = True
            elif i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                i += 1
                options[key] = argv[i]
            else:
                raise CLIError("ArgumentError", f"expected a value for {key}", 0, 2)
        else:
            words.append(arg)
        i += 1
    return " ".join(words), options


def public_data(value):
    if isinstance(value, dict):
        return {key: public_data(item) for key, item in value.items() if not key.startswith("_")}
    if isinstance(value, list):
        return [public_data(item) for item in value]
    return value


def render(value, options):
    value = public_data(value)
    if "--query" in options:
        try:
            value = jmespath.search(options["--query"], value)
        except jmespath.exceptions.JMESPathError as error:
            raise CLIError("QueryError", str(error), 0, 2) from error
    output = options.get("--output", "json")
    if output == "none":
        return ""
    if output in ("json", "jsonc"):
        return json.dumps(value, indent=2) + "\n" if value is not None else ""
    if output == "tsv":
        rows = value if isinstance(value, list) else [value]
        def cell(v):
            return "" if v is None else str(v).lower() if isinstance(v, bool) else str(v)
        return "".join("\t".join(cell(v) for v in (list(r.values()) if isinstance(r, dict) else r if isinstance(r, list) else [r])) + "\n" for r in rows)
    if output == "table":
        rows = value if isinstance(value, list) else [value]
        if not rows:
            return ""
        if not isinstance(rows[0], dict):
            return render(rows, {"--output": "tsv"})
        keys = [k for k, v in rows[0].items() if not isinstance(v, (dict, list))]
        return "\t".join(keys) + "\n" + "".join("\t".join(str(r.get(k, "")) for k in keys) + "\n" for r in rows)
    raise CLIError("ArgumentError", f"unsupported mock output format: {output}", 0, 2)


class Simulator:
    def __init__(self, scenario, skills=False, log_path=None, latency_scale=1.0, docs_mode="off"):
        self.scenario = copy.deepcopy(scenario)
        self.state = copy.deepcopy(scenario["state"])
        self.skills = skills
        self.log_path = Path(log_path) if log_path else None
        self.events = []
        self.lock = threading.Lock()
        self.started = time.monotonic()
        self.latency_scale = latency_scale
        self.first_goal_s = None
        self.verified_goal_s = None
        self.maintenance_observations = {}
        self.docs_mode = docs_mode

    def state_hash(self):
        return hashlib.sha256(json.dumps({"clusters": self.state["clusters"], "providers": self.state.get("providers")}, sort_keys=True).encode()).hexdigest()

    def advance(self):
        now = time.monotonic()
        remaining = []
        for operation in self.state["pending"]:
            if operation["ready"] <= now:
                self.state["clusters"] = operation["clusters"]
            else:
                remaining.append(operation)
        self.state["pending"] = remaining

    def call(self, argv, tool="az"):
        if tool != "az":
            return self.external_call(tool, argv)
        with self.lock:
            start = time.monotonic()
            self.advance()
            before = self.state_hash()
            event = {"sequence": len(self.events) + 1, "started_at": time.time(),
                     "start_s": start - self.started, "argv": argv, "command": "", "tool": "az",
                     "category": "local", "modeled_api_requests": 0, "http_status": None}
            response = {"stdout": "", "stderr": "", "exit_code": 0}
            snapshot = copy.deepcopy(self.state["clusters"])
            pending_snapshot = copy.deepcopy(self.state["pending"])
            providers_snapshot = copy.deepcopy(self.state.get("providers"))
            opts = {}
            try:
                command, opts = parse(argv)
                event["command"] = command
                if len(argv) >= 2 and argv[0] == "aks" and argv[1] in ("skill", "skills"):
                    event["category"] = "skill"
                    event["command"] = " ".join(["aks", "skill", *argv[2:3]])
                    if not self.skills:
                        raise CLIError("CommandNotFound", "'skill' is not in the 'az aks' command group", 0, 2)
                    # Exercise the actual prototype parser/renderer, not a second approximation.
                    env = {**os.environ, "AZ_AKS_SKILLS_DIR": str(ROOT / "skills")}
                    result = subprocess.run([sys.executable, str(ROOT.parent / "bin" / "az"), *argv],
                                            capture_output=True, text=True, env=env, timeout=10)
                    response.update(stdout=result.stdout, stderr=result.stderr, exit_code=result.returncode)
                elif opts.get("--help") or command in ("", "aks", "aks nodepool"):
                    response["stdout"] = self.help(command)
                elif command in ("version",) or "--version" in opts:
                    response["stdout"] = '{"azure-cli": "2.86.0", "mock": true}\n'
                elif command in ("account show", "account list"):
                    account = {"id": "00000000-0000-0000-0000-000000000001", "name": "Benchmark", "state": "Enabled", "isDefault": True}
                    response["stdout"] = render([account] if command.endswith("list") else account, opts)
                elif command == "account set":
                    response["stdout"] = ""
                elif command not in COMMANDS and command not in AUXILIARY:
                    if not command.startswith("aks "):
                        event["category"] = "coverage_gap"
                    raise CLIError("CommandNotFound", f"'{command}' is not a recognized command in this simulator", 0, 2)
                else:
                    self.state["calls"][command] = self.state["calls"].get(command, 0) + 1
                    count = self.state["calls"][command]
                    scripted = next((r for r in self.scenario.get("responses", [])
                                     if r["command"] == command and all(opts.get(k) == v for k, v in r.get("match", {}).items())
                                     and (not r.get("occurrences") or count in r["occurrences"])), None)
                    if command not in SEMANTIC and command not in AUXILIARY and not scripted:
                        event["category"] = "coverage_gap"
                        raise CLIError("MockNotImplemented", f"'{command}' is recognized but requires a scenario response fixture", 0, 2)
                    if command in SEMANTIC or command in AUXILIARY:
                        unknown = set(opts) - FLAGS - VALUES
                        if unknown:
                            event["category"] = "coverage_gap"
                            raise CLIError("MockUnsupportedArguments", f"arguments outside the modeled subset: {' '.join(sorted(unknown))}", 0, 2)
                    event.update(category="azure", modeled_api_requests=1, http_status=200)
                    time.sleep(self.scenario.get("latency_ms", 0) / 1000 * self.latency_scale)
                    for fault in self.scenario.get("faults", []):
                        if fault["command"] == command and count in fault.get("occurrences", [1]) and all(opts.get(k) == v for k, v in fault.get("match", {}).items()):
                            raise CLIError(fault["code"], fault["message"], fault.get("status", 500))
                    if scripted:
                        if scripted.get("error"):
                            err = scripted["error"]
                            raise CLIError(err["code"], err["message"], err.get("status", 400))
                        if "clusters" in scripted:
                            self.state["clusters"] = copy.deepcopy(scripted["clusters"])
                        value = copy.deepcopy(scripted.get("output"))
                        event["modeled_api_requests"] = scripted.get("api_requests", 1)
                    else:
                        value = self.execute(command, opts)
                    changed = self.state["clusters"] != snapshot
                    if changed and not command.endswith(" wait"):
                        event["modeled_api_requests"] += 2  # write + poll + final GET, explicit model
                        delay = self.scenario.get("operation_delay_ms", 0) / 1000 * self.latency_scale
                        if opts.get("--no-wait"):
                            final = copy.deepcopy(self.state["clusters"])
                            self.state["clusters"] = copy.deepcopy(snapshot)
                            for c in self.state["clusters"]:
                                c["provisioningState"] = "Updating"
                            self.state["pending"].append({"ready": time.monotonic() + delay, "clusters": final})
                            value = None
                            event["modeled_api_requests"] = 1
                        else:
                            time.sleep(delay)
                    response["stdout"] = render(value, opts)
            except CLIError as error:
                self.state["clusters"] = snapshot
                self.state["pending"] = pending_snapshot
                if providers_snapshot is not None:
                    self.state["providers"] = providers_snapshot
                else:
                    self.state.pop("providers", None)
                response.update(stderr=f"ERROR: ({error.code}) {error}\n", exit_code=error.exit_code)
                event.update(error_code=error.code, http_status=error.status or None)
                if error.code.startswith("Mock"):
                    event["category"] = "coverage_gap"
            except (ValueError, KeyError, TypeError) as error:
                self.state["clusters"] = snapshot
                self.state["pending"] = pending_snapshot
                if providers_snapshot is not None:
                    self.state["providers"] = providers_snapshot
                else:
                    self.state.pop("providers", None)
                response.update(stderr=f"ERROR: (ArgumentError) {error}\n", exit_code=2)
                event["error_code"] = "ArgumentError"
            end = time.monotonic()
            goal = grade(self.scenario, self.state)["success"]
            if goal and self.first_goal_s is None:
                self.first_goal_s = end - self.started
            read = event["command"] == "aks show"
            if self.scenario["name"] in ("manual-scale", "transient-scale", "autoscaler", "debug-version-skew"):
                read = read or event["command"] == "aks nodepool list" or (
                    event["command"] == "aks nodepool show" and
                    opts.get("--name", opts.get("--nodepool-name")) == "apps")
            if self.scenario["name"] == "automatic-maintenance":
                configs = self.state["clusters"][0].get("_maintenanceConfigurations", {}) if self.state["clusters"] else {}
                if response["exit_code"] == 0 and response["stdout"].strip():
                    if event["command"] == "aks maintenanceconfiguration list":
                        self.maintenance_observations.update(copy.deepcopy(configs))
                    elif event["command"] == "aks maintenanceconfiguration show" and opts.get("--name") in configs:
                        self.maintenance_observations[opts["--name"]] = copy.deepcopy(configs[opts["--name"]])
                read = all(name in configs and self.maintenance_observations.get(name) == configs[name]
                           for name in (automatic.AUTO_SCHEDULE, automatic.OS_SCHEDULE))
            if self.scenario["name"] == "debug-managed-namespace-quota":
                read = False  # A Kubernetes workload read must verify the repaired rollout.
            if goal and response["exit_code"] == 0 and read and response["stdout"].strip():
                self.verified_goal_s = self.verified_goal_s or end - self.started
            event.update(end_s=end - self.started, duration_ms=(end - start) * 1000,
                         exit_code=response["exit_code"], state_before=before, state_after=self.state_hash(),
                         goal_satisfied=goal, stdout_bytes=len(response["stdout"].encode()))
            self.events.append(event)
            if self.log_path:
                with self.log_path.open("a") as stream:
                    stream.write(json.dumps(event) + "\n")
            return response

    def external_call(self, tool, argv):
        with self.lock:
            start = time.monotonic()
            self.advance()
            snapshot = copy.deepcopy(self.state["clusters"])
            event = {"sequence": len(self.events) + 1, "started_at": time.time(), "start_s": start - self.started,
                     "argv": argv, "tool": tool, "command": " ".join([tool, *argv[:2]]),
                     "category": "documentation" if tool == "curl" else "kubernetes",
                     "modeled_api_requests": 0, "modeled_kubernetes_requests": 0,
                     "documentation_http_requests": 0, "state_before": self.state_hash()}
            response = {"stdout": "", "stderr": "", "exit_code": 0}
            verified = False
            try:
                if tool == "curl":
                    if self.docs_mode != "live":
                        raise ValueError("documentation access is disabled for this trial")
                    directory = self.log_path.parent / "documents" if self.log_path else None
                    response["stdout"], metadata = documentation.fetch(argv, directory, metrics=event)
                    event.update(metadata)
                elif tool == "kubectl":
                    if not self.state["clusters"]:
                        raise CLIError("MockNotImplemented", "no Kubernetes fixture is available", 0, 2)
                    event["modeled_kubernetes_requests"] = 1
                    response["stdout"], verified = troubleshooting.kubectl(self.state["clusters"][0], argv, CLIError)
                else:
                    raise ValueError("unsupported benchmark tool")
            except CLIError as error:
                self.state["clusters"] = snapshot
                response.update(stderr=f"Error ({error.code}): {error}\n", exit_code=error.exit_code)
                event.update(error_code=error.code, http_status=error.status)
                if error.code.startswith("Mock"):
                    event["category"] = "coverage_gap"
                    event["modeled_kubernetes_requests"] = 0
            except (OSError, ValueError) as error:
                self.state["clusters"] = snapshot
                response.update(stderr=f"{tool}: {error}\n", exit_code=22 if tool == "curl" else 2)
                event["error_code"] = "DocumentationError" if tool == "curl" else "ArgumentError"
                event["http_status"] = getattr(error, "code", None)
            end = time.monotonic()
            goal = grade(self.scenario, self.state)["success"]
            if goal:
                self.first_goal_s = self.first_goal_s or end - self.started
                if verified and response["exit_code"] == 0:
                    self.verified_goal_s = self.verified_goal_s or end - self.started
            event.update(end_s=end - self.started, duration_ms=(end - start) * 1000,
                         exit_code=response["exit_code"], state_after=self.state_hash(), goal_satisfied=goal,
                         stdout_bytes=len(response["stdout"].encode()))
            self.events.append(event)
            if self.log_path:
                with self.log_path.open("a") as stream:
                    stream.write(json.dumps(event) + "\n")
            return response

    def help(self, command):
        text = self.base_help(command)
        if command.startswith("aks namespace"):
            text += "\nReference: " + documentation.NAMESPACE_URL + "\n"
        elif command in ("aks upgrade", "aks nodepool upgrade"):
            text += "\nReference: " + documentation.VERSION_URL + "\n"
        elif command == "aks create":
            text += "\nReference: " + documentation.PROVIDER_URL + "\n"
        return patch_aks_help(text, command) if self.skills and (command == "aks" or command.startswith("aks ")) else text

    def base_help(self, command):
        if command == "":
            return "Group\n    az : Azure command-line interface.\n\nSubgroups:\n    aks : Azure Kubernetes Service.\n    account : Manage subscription information.\n"
        if command.startswith("aks namespace "):
            return (f"Command: az {command}\nArguments: --resource-group -g; --cluster-name; --name -n; "
                    "--cpu-request; --cpu-limit; --memory-request; --memory-limit; --ingress-policy; --egress-policy; --query; --output -o\n")
        if command.startswith("aks maintenanceconfiguration "):
            return (f"Command: az {command}\nArguments: --resource-group -g; --cluster-name; --name -n; "
                    "--schedule-type Weekly; --day-of-week; --interval-weeks; --duration (4-24 hours); "
                    "--start-time HH:MM; --utc-offset +HH:MM; --start-date YYYY-MM-DD; --query; --output -o\n")
        if command in COMMANDS:
            return (f"Command: az {command}\nArguments: --resource-group -g; --name -n; "
                    "--cluster-name; --nodepool-name; --node-count; --kubernetes-version; "
                    "--enable-cluster-autoscaler; --disable-cluster-autoscaler; "
                    "--update-cluster-autoscaler; --min-count; --max-count; --control-plane-only; "
                    "--no-wait; --yes; --query; --output {json,table,tsv,none}\n" +
                    ("Automatic arguments: --sku {base,automatic}; --tier {free,standard,premium}; "
                     "--enable-hosted-system; --node-provisioning-mode; --auto-upgrade-channel; "
                     "--node-os-upgrade-channel\n" if command in ("aks create", "aks update") else ""))
        prefix = command + " "
        children = [c[len(prefix):] for c in COMMANDS if c.startswith(prefix)]
        groups = sorted({c.split()[0] for c in children if " " in c})
        leaves = sorted(c for c in children if " " not in c)
        text = f"Group\n    az {command} : Azure Kubernetes Service commands.\n\n"
        if groups:
            text += "Subgroups:\n" + "".join(f"    {g:<26} : Manage {g.replace('-', ' ')}.\n" for g in groups) + "\n"
        if leaves:
            text += "Commands:\n" + "".join(f"    {c:<26} : {c.replace('-', ' ').capitalize()}.\n" for c in leaves) + "\n"
        return text

    def execute(self, command, options):
        def need(key):
            if key not in options:
                raise CLIError("ArgumentError", f"required argument: {key}", 0, 2)
            return options[key]
        if command in ("group show", "group exists"):
            name = options.get("--name", options.get("--resource-group"))
            if not name:
                raise CLIError("ArgumentError", "required argument: --name", 0, 2)
            group = next((g for g in self.state.get("resource_groups", []) if g["name"] == name), None)
            if command == "group exists":
                return group is not None
            if not group:
                raise CLIError("ResourceGroupNotFound", f"resource group '{name}' not found", 404)
            return group
        if command in ("provider show", "provider register", "provider list"):
            providers = self.state.get("providers", {"Microsoft.ContainerService": "Registered", "Microsoft.PolicyInsights": "Registered"})
            if command == "provider list":
                return [{"namespace": ns, "registrationState": state} for ns, state in providers.items()]
            namespace = need("--namespace")
            if namespace not in ("Microsoft.ContainerService", "Microsoft.PolicyInsights"):
                raise CLIError("MockNotImplemented", f"provider fixture not available for {namespace}", 0, 2)
            if command == "provider register":
                self.state.setdefault("providers", dict(providers))[namespace] = "Registered"
                providers = self.state["providers"]
            return {"namespace": namespace, "registrationState": providers[namespace]}
        if command == "aks list":
            return [c for c in self.state["clusters"] if not options.get("--resource-group") or c["resourceGroup"] == options["--resource-group"]]
        if command == "aks get-versions":
            return {"values": [{"version": v, "isPreview": False} for v in self.state["upgrades"]]}
        nodepool = command.startswith("aks nodepool ")
        maintenance = command.startswith("aks maintenanceconfiguration ")
        namespace = command.startswith("aks namespace ")
        rg = need("--resource-group")
        name = need("--cluster-name" if nodepool or maintenance or namespace else "--name")
        cluster = next((c for c in self.state["clusters"] if c["name"] == name and c["resourceGroup"] == rg), None)
        if command == "aks create":
            if cluster:
                raise CLIError("Conflict", "cluster already exists", 409)
            template = copy.deepcopy(self.scenario["cluster_template"] if "cluster_template" in self.scenario
                                     else self.scenario["initial_state"]["clusters"][0])
            template.update(name=name, resourceGroup=rg, location=options.get("--location", "eastus"))
            template["id"] = f"/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/{rg}/providers/Microsoft.ContainerService/managedClusters/{name}"
            version = options.get("--kubernetes-version", template["kubernetesVersion"])
            template.update(kubernetesVersion=version, currentKubernetesVersion=version,
                            nodeResourceGroup=f"MC_{rg}_{name}_{template['location']}")
            sku = options.get("--sku", "base").lower()
            if sku not in ("base", "automatic"):
                raise CLIError("InvalidParameter", "sku must be base or automatic")
            if sku == "automatic":
                if self.state.get("providers", {}).get("Microsoft.PolicyInsights", "Registered") != "Registered":
                    raise CLIError("MissingSubscriptionRegistration", "The subscription is not registered to use namespace Microsoft.PolicyInsights. " + documentation.PROVIDER_URL)
                self.validate_automatic_options(options)
                template = automatic.automatic_defaults(template)
                self.state["clusters"].append(template)
                return template
            template["sku"] = {"name": "Base", "tier": options.get("--tier", "free").title()}
            pool = template["agentPoolProfiles"][0]
            count = int(options.get("--node-count", 3))
            if count < 2:
                raise CLIError("ValidationError", "system pool requires at least two nodes")
            pool.update(name=options.get("--nodepool-name", "nodepool1"), count=count,
                        orchestratorVersion=version, currentOrchestratorVersion=version,
                        vmSize=options.get("--node-vm-size", "Standard_D4s_v5"))
            if options.get("--enable-cluster-autoscaler"):
                low, high = int(need("--min-count")), int(need("--max-count"))
                if low < 0 or high < max(1, low):
                    raise CLIError("ValidationError", "invalid autoscaler min/max bounds")
                pool.update(enableAutoScaling=True, minCount=low, maxCount=high)
            template["agentPoolProfiles"] = [pool]
            self.state["clusters"].append(template)
            return template
        if not cluster:
            raise CLIError("ResourceNotFound", f"Managed cluster '{name}' in resource group '{rg}' was not found", 404)
        action = command.split()[-1]
        mutation = action not in ("show", "list", "get-upgrades", "wait")
        if mutation and self.state["pending"]:
            raise CLIError("OperationNotAllowed", "another operation is in progress", 409)
        if mutation and action not in ("start", "delete") and cluster["powerState"]["code"] != "Running":
            raise CLIError("OperationNotAllowed", "start the stopped cluster before changing it", 409)
        if maintenance:
            return self.maintenance(cluster, action, options)
        if namespace:
            return troubleshooting.namespace_command(cluster, action, options, CLIError)
        if command == "aks delete":
            self.state["clusters"].remove(cluster)
            return None
        if command in ("aks show", "aks nodepool list"):
            return cluster["agentPoolProfiles"] if nodepool else cluster
        if action == "wait":
            if self.state["pending"]:
                timeout = float(options.get("--timeout", 30))
                delay = max(p["ready"] for p in self.state["pending"]) - time.monotonic()
                if delay > timeout:
                    raise CLIError("Timeout", "operation did not complete before timeout", 408)
                time.sleep(max(0, delay))
                self.advance()
            return None
        target = cluster
        if nodepool or action == "scale":
            pool_name = options.get("--name") if nodepool else options.get("--nodepool-name")
            pool_name = options.get("--nodepool-name", pool_name)
            if not pool_name:
                raise CLIError("ArgumentError", "specify the node pool name", 0, 2)
            target = next((p for p in cluster["agentPoolProfiles"] if p["name"] == pool_name), None)
            if action == "add":
                if target:
                    raise CLIError("Conflict", "node pool already exists", 409)
                templates = cluster["agentPoolProfiles"] or self.scenario.get("cluster_template", {}).get("agentPoolProfiles", [])
                if not templates:
                    raise CLIError("MockNotImplemented", "node pool creation needs a pool template", 0, 2)
                target = copy.deepcopy(templates[0])
                target.update(name=pool_name, mode=options.get("--mode", "User"), count=int(options.get("--node-count", 3)))
                target.update(enableAutoScaling=False, minCount=None, maxCount=None)
                if target["count"] < (2 if target["mode"] == "System" else 0):
                    raise CLIError("ValidationError", "node count is below the pool minimum")
                cluster["agentPoolProfiles"].append(target)
                return target
            if target is None:
                raise CLIError("ResourceNotFound", f"node pool '{pool_name}' was not found", 404)
            if action == "show":
                return target
            if action == "delete":
                if target["mode"] == "System" and sum(p["mode"] == "System" for p in cluster["agentPoolProfiles"]) == 1:
                    raise CLIError("ValidationError", "cannot delete the last system pool")
                cluster["agentPoolProfiles"].remove(target)
                return None
        if action == "get-upgrades":
            upgrades = [{"kubernetesVersion": v, "isPreview": False} for v in self.state["upgrades"]]
            result = {"kubernetesVersion": cluster["kubernetesVersion"], "upgrades": upgrades}
            return result if nodepool else {"name": "default", "controlPlaneProfile": result, "agentPoolProfiles": []}
        if action == "start":
            target["powerState"]["code"] = "Running"
            return None
        if action == "stop":
            if cluster.get("nodeProvisioningProfile", {}).get("mode") == "Auto":
                raise CLIError("OperationNotAllowed", "stop is not supported with node auto-provisioning")
            if nodepool and target["mode"] == "System":
                raise CLIError("OperationNotAllowed", "system node pools cannot be stopped")
            target["powerState"]["code"] = "Stopped"
            return None
        if action == "scale":
            if target["enableAutoScaling"]:
                raise CLIError("BadRequest", "Cannot scale cluster autoscaler enabled node pool. Disable autoscaling or update its bounds.")
            count = int(need("--node-count"))
            if count < (2 if target["mode"] == "System" else 0):
                raise CLIError("ValidationError", "node count is below the pool minimum")
            target["count"] = count
        elif action == "update":
            if not nodepool:
                if cluster.get("sku", {}).get("name") == "Automatic":
                    self.validate_automatic_options(options)
                    return cluster
                target = cluster["agentPoolProfiles"][0]
            if options.get("--disable-cluster-autoscaler"):
                target["enableAutoScaling"] = False
            if options.get("--update-cluster-autoscaler") and not target["enableAutoScaling"]:
                raise CLIError("BadRequest", "autoscaler is disabled; use --enable-cluster-autoscaler")
            if options.get("--enable-cluster-autoscaler"):
                target["enableAutoScaling"] = True
            if options.get("--enable-cluster-autoscaler") or options.get("--update-cluster-autoscaler"):
                low, high = int(need("--min-count")), int(need("--max-count"))
                if low < 0 or high < max(1, low):
                    raise CLIError("ValidationError", "invalid autoscaler min/max bounds")
                target.update(minCount=low, maxCount=high)
        elif action == "upgrade":
            version = need("--kubernetes-version")
            if version not in self.state["upgrades"]:
                raise CLIError("KubernetesVersionNotSupported", "target is not in the available upgrade list")
            if nodepool:
                if tuple(map(int, version.split("."))) > tuple(map(int, cluster["kubernetesVersion"].split("."))):
                    raise CLIError("NodePoolMcVersionIncompatible", f"Node pool version {version} is greater than control plane version {cluster['kubernetesVersion']}. " + documentation.VERSION_URL)
                target.update(orchestratorVersion=version, currentOrchestratorVersion=version, provisioningState="Succeeded")
            else:
                if options.get("--control-plane-only") and cluster["autoUpgradeProfile"].get("upgradeChannel") not in (None, "none"):
                    raise CLIError("OperationNotAllowed", "control-plane-only is incompatible with cluster autoupgrade")
                cluster.update(kubernetesVersion=version, currentKubernetesVersion=version)
                if not options.get("--control-plane-only"):
                    for pool in cluster["agentPoolProfiles"]:
                        pool.update(orchestratorVersion=version, currentOrchestratorVersion=version)
        return target if nodepool else cluster

    @staticmethod
    def validate_automatic_options(options):
        required = {"--sku": "automatic", "--tier": "standard", "--node-provisioning-mode": "auto",
                    "--auto-upgrade-channel": "stable", "--node-os-upgrade-channel": "nodeimage",
                    "--network-plugin": "azure", "--network-plugin-mode": "overlay", "--network-dataplane": "cilium",
                    "--network-policy": "cilium", "--outbound-type": "managednatgateway"}
        for key, expected in required.items():
            if key in options and str(options[key]).lower() != expected:
                if key == "--sku":
                    raise CLIError("MockNotImplemented", "Automatic migration is outside this fixture", 0, 2)
                raise CLIError("InvalidParameter", f"Automatic managed-network fixture requires {key} {expected}")
        if any(key in options for key in ("--node-count", "--min-count", "--max-count", "--node-vm-size",
                                           "--enable-cluster-autoscaler", "--disable-cluster-autoscaler",
                                           "--update-cluster-autoscaler")):
            raise CLIError("InvalidParameter", "use Automatic node provisioning rather than fixed pool capacity or cluster autoscaler settings")
        if options.get("--enable-hosted-system", True) not in (True, "true"):
            raise CLIError("InvalidParameter", "new Automatic clusters use managed system node pools")

    @staticmethod
    def maintenance(cluster, action, options):
        configs = cluster.get("_maintenanceConfigurations", {})
        if action == "list":
            return [configs[name] for name in sorted(configs)]
        name = options.get("--name")
        if not name:
            raise CLIError("ArgumentError", "required argument: --name", 0, 2)
        if action == "show":
            if name not in configs:
                raise CLIError("ResourceNotFound", f"maintenance configuration '{name}' not found", 404)
            return configs[name]
        if action == "delete":
            configs.pop(name, None)
            return None
        if action == "update" and name not in configs:
            raise CLIError("ResourceNotFound", f"maintenance configuration '{name}' not found", 404)
        if name not in ("default", automatic.AUTO_SCHEDULE, automatic.OS_SCHEDULE):
            raise CLIError("InvalidParameter", "use default, aksManagedAutoUpgradeSchedule or aksManagedNodeOSUpgradeSchedule")
        current = copy.deepcopy(configs.get(name, {"id": f"{cluster['id']}/maintenanceConfigurations/{name}",
                                                  "name": name, "resourceGroup": cluster["resourceGroup"],
                                                  "maintenanceWindow": {}}))
        w = current["maintenanceWindow"]
        weekly = w.get("schedule", {}).get("weekly", {})
        if options.get("--schedule-type", "Weekly").lower() != "weekly":
            raise CLIError("MockNotImplemented", "only weekly schedules are modeled", 0, 2)
        day = options.get("--day-of-week", weekly.get("dayOfWeek", ""))
        if day not in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"):
            raise CLIError("InvalidParameter", "specify a valid --day-of-week")
        interval = int(options.get("--interval-weeks", weekly.get("intervalWeeks", 1)))
        duration = int(options.get("--duration", w.get("durationHours", 4)))
        start = options.get("--start-time", w.get("startTime", ""))
        offset = options.get("--utc-offset", w.get("utcOffset", "+00:00"))
        if interval < 1 or not 4 <= duration <= 24 or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", start):
            raise CLIError("InvalidParameter", "use a positive weekly interval, 4-24 hour duration and HH:MM start time")
        if not re.fullmatch(r"[+-](?:0\d|1[0-3]):[0-5]\d|[+-]14:00", offset):
            raise CLIError("InvalidParameter", "invalid UTC offset")
        w.update(schedule={"weekly": {"intervalWeeks": interval, "dayOfWeek": day}},
                 durationHours=duration, startTime=start, utcOffset=offset)
        if "--start-date" in options:
            from datetime import date
            date.fromisoformat(options["--start-date"])
            w["startDate"] = options["--start-date"]
        cluster.setdefault("_maintenanceConfigurations", {})[name] = current
        return current
