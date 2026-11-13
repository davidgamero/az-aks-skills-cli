"""Automatic fixtures and independent oracles, based on linked Microsoft Learn docs."""

import copy

NAMES = ("automatic-create", "automatic-maintenance")
AUTO_SCHEDULE = "aksManagedAutoUpgradeSchedule"
OS_SCHEDULE = "aksManagedNodeOSUpgradeSchedule"


def automatic_defaults(cluster):
    """Model managed-network Automatic fields, not workload provisioning."""
    cluster = copy.deepcopy(cluster)
    cluster.update(
        sku={"name": "Automatic", "tier": "Standard"},
        hostedSystemProfile={"enabled": True, "nodeSubnetId": None, "systemNodeSubnetId": None},
        nodeProvisioningProfile={"mode": "Auto"},
        autoUpgradeProfile={"upgradeChannel": "stable", "nodeOSUpgradeChannel": "NodeImage"},
        networkProfile={"networkPlugin": "azure", "networkPluginMode": "overlay",
                        "networkDataplane": "cilium", "networkPolicy": "cilium",
                        "outboundType": "managedNATGateway", "loadBalancerSku": "standard"},
        identity={"type": "SystemAssigned"},
        oidcIssuerProfile={"enabled": True},
        securityProfile={"workloadIdentity": {"enabled": True}},
        agentPoolProfiles=[],
    )
    return cluster


def window(cluster, name, day, start):
    return {"id": f"{cluster['id']}/maintenanceConfigurations/{name}", "name": name,
            "resourceGroup": cluster["resourceGroup"],
            "maintenanceWindow": {
                "schedule": {"weekly": {"intervalWeeks": 1, "dayOfWeek": day}},
                "durationHours": 4, "startTime": start, "utcOffset": "+00:00",
            }}


def make(name, seed, base):
    scenario = copy.deepcopy(base)
    template = copy.deepcopy(base["state"]["clusters"][0])
    suffix = template["name"].rsplit("-", 1)[1]
    old_name = template["name"]
    template["name"] = f"aks-auto-{suffix}"
    template["id"] = template["id"].rsplit("/", 1)[0] + "/" + template["name"]
    template["nodeResourceGroup"] = template["nodeResourceGroup"].replace(old_name, template["name"])
    target = {key: template[key] for key in ("name", "resourceGroup", "location", "id")}
    scenario.update(name=name, seed=seed, target=target, cluster_template=template, faults=[], responses=[])
    scenario["state"] = {"clusters": [], "upgrades": ["1.34.2"], "calls": {}, "pending": [],
                         "resource_groups": [{"name": target["resourceGroup"], "location": "eastus",
                                              "properties": {"provisioningState": "Succeeded"}}]}
    if name == "automatic-create":
        task = (f"Create a new AKS Automatic cluster named {target['name']} in the existing resource group "
                f"{target['resourceGroup']} in eastus. Use AKS-managed networking and managed system node pools, "
                "retaining the Automatic defaults for node provisioning and upgrade channels. "
                "The required resource providers are already registered. Verify the cluster SKU, "
                "managed-system status, provisioning mode and upgrade channels. "
                "Do not deploy workloads or create manually sized node pools.")
        scenario["source"] = "https://learn.microsoft.com/en-us/azure/aks/automatic/quick-automatic-managed-network"
    else:
        cluster = automatic_defaults(template)
        cluster["_maintenanceConfigurations"] = {
            "default": window(cluster, "default", "Monday", "01:00"),
            AUTO_SCHEDULE: window(cluster, AUTO_SCHEDULE, "Wednesday", "10:00"),
            OS_SCHEDULE: window(cluster, OS_SCHEDULE, "Thursday", "11:00"),
        }
        scenario["state"]["clusters"] = [cluster]
        task = (f"On the existing AKS Automatic cluster {target['name']} in {target['resourceGroup']}, "
                "schedule Kubernetes auto-upgrades every Sunday from 02:00 to 06:00 UTC and node OS/image "
                "upgrades every Saturday from 03:00 to 07:00 UTC. Keep the existing upgrade channels, "
                "Automatic SKU, node provisioning, and unrelated default maintenance configuration unchanged. "
                "Verify both schedules. Do not start an upgrade now.")
        scenario["source"] = "https://learn.microsoft.com/en-us/azure/aks/planned-maintenance"
    scenario["prompt"] = task + (" Use the available CLI to carry out the task and verify the resulting state. "
                                "Do not just provide instructions. Report what you changed and the final state. "
                                "The CLI is already authenticated. Work autonomously with the information provided.")
    scenario["initial_state"] = copy.deepcopy(scenario["state"])
    return scenario


def grade(scenario, state):
    target = scenario["target"]
    cluster = next((c for c in state["clusters"] if c["id"] == target["id"]), None)
    checks = {"target_cluster_exists": cluster is not None, "only_target_cluster": len(state["clusters"]) == 1,
              "no_pending_operation": not state["pending"]}
    if not cluster:
        return {"success": False, "checks": checks}
    checks.update(
        correct_location=cluster["location"] == target["location"],
        provisioning_succeeded=cluster["provisioningState"] == "Succeeded",
        automatic_sku=cluster.get("sku", {}).get("name") == "Automatic",
        standard_tier=cluster.get("sku", {}).get("tier") == "Standard",
        managed_system=cluster.get("hostedSystemProfile", {}).get("enabled") is True,
        nap_enabled=cluster.get("nodeProvisioningProfile", {}).get("mode") == "Auto",
        stable_channel=cluster.get("autoUpgradeProfile", {}).get("upgradeChannel") == "stable",
        node_image_channel=cluster.get("autoUpgradeProfile", {}).get("nodeOSUpgradeChannel") == "NodeImage",
        no_manual_pools=cluster.get("agentPoolProfiles") == [],
        running=cluster["powerState"]["code"] == "Running",
    )
    if scenario["name"] == "automatic-create":
        network = cluster.get("networkProfile", {})
        checks["managed_network_defaults"] = all(network.get(k) == v for k, v in {
            "networkPlugin": "azure", "networkPluginMode": "overlay", "networkDataplane": "cilium",
            "outboundType": "managedNATGateway",
        }.items())
    else:
        initial = scenario["initial_state"]["clusters"][0]
        configs = cluster.get("_maintenanceConfigurations", {})
        checks["cluster_unchanged"] = {k: v for k, v in cluster.items() if not k.startswith("_")} == {
            k: v for k, v in initial.items() if not k.startswith("_")}
        checks["same_configuration_names"] = set(configs) == {"default", AUTO_SCHEDULE, OS_SCHEDULE}
        checks["default_unchanged"] = configs.get("default") == initial["_maintenanceConfigurations"]["default"]
        for config, day, start in ((AUTO_SCHEDULE, "Sunday", "02:00"), (OS_SCHEDULE, "Saturday", "03:00")):
            w = configs.get(config, {}).get("maintenanceWindow", {})
            checks[config] = (w.get("schedule") == {"weekly": {"intervalWeeks": 1, "dayOfWeek": day}}
                              and w.get("startTime") == start and w.get("durationHours") == 4
                              and w.get("utcOffset") == "+00:00")
    return {"success": all(checks.values()), "checks": checks}


def oracle_commands(scenario):
    target = scenario["target"]
    cluster = ["-g", target["resourceGroup"], "-n", target["name"]]
    if scenario["name"] == "automatic-create":
        return [["aks", "create", *cluster, "--location", "eastus", "--sku", "automatic", "--enable-hosted-system"],
                ["aks", "show", *cluster]]
    base = ["-g", target["resourceGroup"], "--cluster-name", target["name"]]
    commands = [["aks", "show", *cluster], ["aks", "maintenanceconfiguration", "list", *base]]
    for config, day, start in ((AUTO_SCHEDULE, "Sunday", "02:00"), (OS_SCHEDULE, "Saturday", "03:00")):
        commands.append(["aks", "maintenanceconfiguration", "update", *base, "-n", config,
                         "--schedule-type", "Weekly", "--day-of-week", day, "--interval-weeks", "1",
                         "--duration", "4", "--start-time", start, "--utc-offset", "+00:00"])
    commands.append(["aks", "maintenanceconfiguration", "list", *base])
    return commands
