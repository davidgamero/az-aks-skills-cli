"""Seeded fixtures, natural task prompts, and host-only state oracles."""

import copy
import random

from . import automatic
from . import troubleshooting
from . import candidate_fixtures, candidate_oracles
from . import investigations


SOURCES = {
    "scale": "https://learn.microsoft.com/en-us/azure/aks/scale-cluster",
    "autoscale": "https://learn.microsoft.com/en-us/azure/aks/cluster-autoscaler",
    "upgrade": "https://learn.microsoft.com/en-us/azure/aks/upgrade-aks-control-plane",
    "stop": "https://learn.microsoft.com/en-us/azure/aks/start-stop-cluster",
}
NAMES = ("manual-scale", "autoscaler", "control-plane-upgrade", "stop-dev", "transient-scale") + automatic.NAMES + troubleshooting.NAMES + candidate_fixtures.NAMES + investigations.NAMES


def make(name: str, seed: int = 1) -> dict:
    if name not in NAMES:
        raise ValueError(f"unknown scenario: {name}")
    if name in investigations.NAMES:
        return investigations.make(name, seed, make("manual-scale", seed))
    if name in candidate_fixtures.NAMES:
        return candidate_fixtures.make(name, seed, make("manual-scale", seed))
    if name in automatic.NAMES:
        return automatic.make(name, seed, make("manual-scale", seed))
    if name in troubleshooting.NAMES:
        base_name = "automatic-create" if name == "debug-automatic-provider" else "manual-scale"
        return troubleshooting.make(name, seed, make(base_name, seed))
    rng = random.Random(seed)
    suffix = rng.randrange(1000, 9999)
    rg, cluster_name = f"rg-dev-{suffix}", f"aks-dev-{suffix}"
    target_count = rng.choice([4, 5, 6])
    version, target_version = "1.33.5", "1.34.2"
    cluster = {
        "id": f"/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/{rg}/providers/Microsoft.ContainerService/managedClusters/{cluster_name}",
        "name": cluster_name, "resourceGroup": rg, "location": "eastus",
        "kubernetesVersion": version, "currentKubernetesVersion": version,
        "provisioningState": "Succeeded", "powerState": {"code": "Running"},
        "nodeResourceGroup": f"MC_{rg}_{cluster_name}_eastus",
        "agentPoolProfiles": [
            {"name": "system", "mode": "System", "count": 3, "enableAutoScaling": False,
             "minCount": None, "maxCount": None, "orchestratorVersion": version,
             "currentOrchestratorVersion": version, "vmSize": "Standard_D4s_v5",
             "osType": "Linux", "provisioningState": "Succeeded", "powerState": {"code": "Running"}},
            {"name": "apps", "mode": "User", "count": 2, "enableAutoScaling": True,
             "minCount": 1, "maxCount": 3, "orchestratorVersion": version,
             "currentOrchestratorVersion": version, "vmSize": "Standard_D4s_v5",
             "osType": "Linux", "provisioningState": "Succeeded", "powerState": {"code": "Running"}},
        ],
        "autoUpgradeProfile": {"upgradeChannel": "none"},
        "tags": {"environment": "development"},
    }
    state = {"clusters": [cluster], "upgrades": [target_version], "calls": {}, "pending": []}
    tasks = {
        "manual-scale": f"Set the apps node pool to a fixed size of {target_count} nodes, with autoscaling disabled. Leave the system pool unchanged.",
        "autoscaler": f"Keep autoscaling enabled on the apps pool and change its bounds to a minimum of 2 and a maximum of {target_count + 3} nodes. Leave the system pool unchanged.",
        "control-plane-upgrade": f"Upgrade only the control plane to Kubernetes {target_version}. Leave all node pool versions unchanged.",
        "stop-dev": "Stop this development cluster to save compute costs. Preserve the cluster and its node pool configuration for a later restart.",
        "transient-scale": f"Set the apps node pool to a fixed size of {target_count} nodes, with autoscaling disabled. Leave the system pool unchanged. Handle transient service failures if they occur.",
    }
    prompt = (f"You are operating AKS cluster {cluster_name} in resource group {rg}. "
              f"{tasks[name]} Use the available CLI to carry out the task and verify the resulting state. "
              "Do not just provide instructions. Report what you changed and the final state. "
              "The CLI is already authenticated. Work autonomously with the information provided.")
    faults = []
    if name == "transient-scale":
        faults = [{"command": "aks nodepool scale", "occurrences": [1],
                   "code": "TooManyRequests", "message": "Request throttled. Retry-After: 1 second.", "status": 429}]
    return {"name": name, "seed": seed, "prompt": prompt, "state": state,
            "initial_state": copy.deepcopy(state), "faults": faults, "responses": [],
            "target_count": target_count, "target_version": target_version,
            "latency_ms": 30, "operation_delay_ms": 150,
            "source": SOURCES[{"manual-scale": "scale", "transient-scale": "scale", "autoscaler": "autoscale",
                               "control-plane-upgrade": "upgrade", "stop-dev": "stop"}[name]]}


def grade(scenario: dict, state: dict) -> dict:
    if scenario.get("suite") == "investigation-v1":
        return investigations.grade(scenario,state)
    if scenario.get("suite") == "candidate-v1":
        return candidate_oracles.grade(scenario, state)
    if scenario["name"] in troubleshooting.NAMES:
        return troubleshooting.grade(scenario, state)
    if scenario["name"] in automatic.NAMES:
        return automatic.grade(scenario, state)
    initial = scenario["initial_state"]["clusters"][0]
    clusters = state["clusters"]
    target = next((c for c in clusters if c["id"] == initial["id"]), None)
    checks = {"cluster_preserved": target is not None, "no_extra_clusters": len(clusters) == 1}
    if not target:
        return {"success": False, "checks": checks}
    pools = {p["name"]: p for p in target["agentPoolProfiles"]}
    checks["same_pools"] = set(pools) == {"apps", "system"}
    checks["system_pool_unchanged"] = pools.get("system") == initial["agentPoolProfiles"][0]
    checks["operation_complete"] = target["provisioningState"] == "Succeeded" and not state["pending"]
    apps = pools.get("apps", {})
    name = scenario["name"]
    if name in ("manual-scale", "transient-scale"):
        checks.update(fixed_count=apps.get("count") == scenario["target_count"],
                      autoscaling_disabled=apps.get("enableAutoScaling") is False)
    elif name == "autoscaler":
        checks.update(autoscaling_enabled=apps.get("enableAutoScaling") is True,
                      minimum=apps.get("minCount") == 2,
                      maximum=apps.get("maxCount") == scenario["target_count"] + 3)
    elif name == "control-plane-upgrade":
        checks["control_plane_version"] = target["kubernetesVersion"] == scenario["target_version"]
        checks["pool_versions_unchanged"] = all(
            pools.get(p["name"], {}).get("orchestratorVersion") == p["orchestratorVersion"]
            for p in initial["agentPoolProfiles"])
    elif name == "stop-dev":
        checks["stopped"] = target["powerState"]["code"] == "Stopped"
        checks["pool_configuration_preserved"] = target["agentPoolProfiles"] == initial["agentPoolProfiles"]
    if name != "control-plane-upgrade":
        checks["version_unchanged"] = target["kubernetesVersion"] == initial["kubernetesVersion"]
    if name != "stop-dev":
        checks["still_running"] = target["powerState"]["code"] == "Running"
    return {"success": all(checks.values()), "checks": checks}
