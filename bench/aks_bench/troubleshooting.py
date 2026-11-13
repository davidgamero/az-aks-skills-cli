"""Persistent fault scenarios and a bounded Kubernetes/managed-namespace model."""

import copy
from decimal import Decimal, InvalidOperation
import json
from datetime import datetime, timedelta, timezone

from . import automatic
from .documentation import VERSION_URL, PROVIDER_URL, NAMESPACE_URL, NAMESPACE_CONCEPTS_URL

NAMES = ("debug-version-skew", "debug-automatic-provider", "debug-managed-namespace-quota")


def cpu(value):
    value = str(value)
    try:
        result = Decimal(value[:-1]) / 1000 if value.endswith("m") else Decimal(value)
        if not result.is_finite():
            raise ValueError("CPU quantity must be finite")
        return result
    except InvalidOperation as error:
        raise ValueError("invalid CPU quantity") from error


def make(name, seed, base):
    scenario = copy.deepcopy(base)
    scenario.update(name=name, faults=[], responses=[])
    c = scenario["state"]["clusters"][0] if scenario["state"]["clusters"] else scenario["cluster_template"]
    if name == "debug-version-skew":
        c["agentPoolProfiles"][1]["provisioningState"] = "Failed"
        task = (f"The previous upgrade of the apps node pool in AKS cluster {c['name']} in {c['resourceGroup']} failed. "
                "Diagnose the failure and finish upgrading apps to Kubernetes 1.34.2. You may upgrade the control "
                "plane if necessary, but leave the system pool and all node counts unchanged. Verify the repaired pool.")
        scenario["source"] = VERSION_URL
    elif name == "debug-automatic-provider":
        scenario["state"]["providers"] = {"Microsoft.ContainerService": "Registered", "Microsoft.PolicyInsights": "NotRegistered"}
        task = (f"The previous attempt to create AKS Automatic cluster {c['name']} in the existing resource group "
                f"{c['resourceGroup']} in eastus failed. Diagnose and resolve the blocker, then create and verify "
                "the cluster using managed networking, managed system pools and Automatic defaults. "
                "You have permission to register required resource providers. Do not deploy workloads.")
        scenario["source"] = PROVIDER_URL
    else:
        c = automatic.automatic_defaults(c)
        scenario["state"]["clusters"] = [c]
        namespace = {"id": c["id"] + "/managedNamespaces/retail", "name": "retail", "location": c["location"],
                     "resourceGroup": c["resourceGroup"], "provisioningState": "Succeeded",
                     "defaultResourceQuota": {"cpuRequest": "2000m", "cpuLimit": "8000m", "memoryRequest": "8Gi", "memoryLimit": "16Gi"},
                     "defaultNetworkPolicy": {"ingress": "AllowSameNamespace", "egress": "AllowAll"},
                     "adoptionPolicy": "IfIdentical", "deletePolicy": "Keep"}
        c["_managedNamespaces"] = {"retail": namespace}
        c["_workload"] = {"name": "api", "namespace": "retail", "replicas": 4, "ready": 2, "cpu_request": "1"}
        task = (f"The api deployment in namespace retail on AKS Automatic cluster {c['name']} in {c['resourceGroup']} "
                "is stuck at two ready replicas after requesting four. Diagnose and restore all four replicas. "
                "The approved namespace CPU-request budget is four cores. Keep per-pod resource requests, "
                "CPU limits, memory quotas, namespace network policies and cluster settings unchanged. "
                "Do not remove the managed namespace or its quota. Verify the rollout. kubectl is already configured.")
        scenario["source"] = NAMESPACE_URL
    scenario["prompt"] = task + " Use the available CLI to carry out the task, not just describe steps. The CLI is authenticated. Work autonomously."
    scenario["initial_state"] = copy.deepcopy(scenario["state"])
    return scenario


def grade(scenario, state):
    name = scenario["name"]
    if name == "debug-automatic-provider":
        delegated = {**scenario, "name": "automatic-create"}
        result = automatic.grade(delegated, state)
        result["checks"]["provider_registered"] = state.get("providers", {}).get("Microsoft.PolicyInsights") == "Registered"
        result["checks"]["other_provider_unchanged"] = state.get("providers", {}).get("Microsoft.ContainerService") == "Registered"
        result["success"] = all(result["checks"].values())
        return result
    initial = scenario["initial_state"]["clusters"][0]
    c = next((c for c in state["clusters"] if c["id"] == initial["id"]), None)
    checks = {"cluster_preserved": c is not None, "no_extra_clusters": len(state["clusters"]) == 1,
              "operations_complete": not state["pending"]}
    if not c:
        return {"success": False, "checks": checks}
    if name == "debug-version-skew":
        pools = {p["name"]: p for p in c["agentPoolProfiles"]}
        apps = pools.get("apps", {})
        checks.update(control_plane_version=c["kubernetesVersion"] == "1.34.2",
                      pool_version=apps.get("orchestratorVersion") == "1.34.2",
                      pool_recovered=apps.get("provisioningState") == "Succeeded",
                      system_unchanged=pools.get("system") == initial["agentPoolProfiles"][0],
                      apps_count_unchanged=apps.get("count") == 2,
                      same_pools=set(pools) == {"system", "apps"})
    else:
        ns = c.get("_managedNamespaces", {}).get("retail", {})
        old = initial["_managedNamespaces"]["retail"]
        quota = ns.get("defaultResourceQuota", {})
        checks["cpu_budget"] = cpu(quota.get("cpuRequest", "0")) == 4
        checks["other_quota_unchanged"] = all(quota.get(k) == v for k, v in old["defaultResourceQuota"].items() if k != "cpuRequest")
        checks["namespace_configuration_preserved"] = {k:v for k,v in ns.items() if k != "defaultResourceQuota"} == {k:v for k,v in old.items() if k != "defaultResourceQuota"}
        checks["cluster_settings_preserved"] = {k:v for k,v in c.items() if not k.startswith("_")} == {k:v for k,v in initial.items() if not k.startswith("_")}
        w = c.get("_workload", {})
        checks.update(four_replicas=w.get("replicas") == 4 and w.get("ready") == 4,
                      per_pod_request_unchanged=w.get("cpu_request") == "1")
    return {"success": all(checks.values()), "checks": checks}


def reconcile(cluster):
    workload = cluster["_workload"]
    quota = cluster["_managedNamespaces"]["retail"]["defaultResourceQuota"]
    workload["ready"] = min(workload["replicas"], int(cpu(quota["cpuRequest"]) / cpu(workload["cpu_request"])))


def namespace_command(cluster, action, options, error):
    namespaces = cluster.get("_managedNamespaces", {})
    if action == "list":
        return list(namespaces.values())
    name = options.get("--name")
    if name not in namespaces:
        raise error("ResourceNotFound", f"managed namespace '{name}' not found", 404)
    ns = namespaces[name]
    if action == "show":
        return ns
    if action != "update":
        raise error("MockNotImplemented", "only namespace list/show/update are modeled", 0, 2)
    for option, field in (("--cpu-request", "cpuRequest"), ("--cpu-limit", "cpuLimit"),
                          ("--memory-request", "memoryRequest"), ("--memory-limit", "memoryLimit")):
        if option in options:
            ns["defaultResourceQuota"][field] = options[option]
    if cpu(ns["defaultResourceQuota"]["cpuRequest"]) <= 0 or cpu(ns["defaultResourceQuota"]["cpuRequest"]) > cpu(ns["defaultResourceQuota"]["cpuLimit"]):
        raise error("InvalidParameter", "CPU request quota must be positive and no greater than CPU limit")
    for option, field in (("--ingress-policy", "ingress"), ("--egress-policy", "egress")):
        if option in options:
            ns["defaultNetworkPolicy"][field] = options[option]
    reconcile(cluster)
    return ns


def kubectl(cluster, argv, error):
    if "--help" in argv or "-h" in argv or not argv:
        return "kubectl get/describe deployment|pods|events|resourcequota|namespace -n NAMESPACE; rollout status deployment/NAME; scale deployment NAME --replicas N\n", False
    if argv[:2] == ["config", "current-context"]:
        return cluster["name"] + "\n", False
    # Kubernetes -n is namespace, unlike az -n (resource name).
    words, opts = [], {}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg.startswith("-"):
            key, eq, value = arg.partition("=")
            key = {"-n": "--namespace", "-o": "--output"}.get(key, key)
            if not eq:
                i += 1
                if i == len(argv):
                    raise error("ArgumentError", f"missing value for {key}", 0, 2)
                value = argv[i]
            opts[key] = value
        else:
            words.extend(arg.split("/", 1))
        i += 1
    action = words[0]
    resource = words[1] if len(words) > 1 else ""
    if action == "get" and "," in resource:
        items, verified = [], False
        index = argv.index(resource)
        for kind in resource.split(","):
            text, read = kubectl(cluster, [*argv[:index], kind, *argv[index + 1:]], error)
            data = json.loads(text)
            items.extend(data["items"] if "items" in data else [data])
            verified = verified or read
        return json.dumps({"apiVersion": "v1", "kind": "List", "items": items}, indent=2) + "\n", verified
    if action in ("get", "describe") and resource in ("node", "nodes"):
        nodes = []
        for pool in cluster["agentPoolProfiles"]:
            for index in range(pool["count"]):
                nodes.append({"apiVersion": "v1", "kind": "Node", "metadata": {"name": f"aks-{pool['name']}-{index}", "labels": {"agentpool": pool["name"]}},
                              "status": {"conditions": [{"type": "Ready", "status": "True"}], "nodeInfo": {"kubeletVersion": "v" + pool["orchestratorVersion"]}}})
        return json.dumps({"kind": "List", "items": nodes}, indent=2) + "\n", True
    if "_workload" not in cluster:
        raise error("MockNotImplemented", "Kubernetes workload state is not modeled for this scenario", 0, 2)
    if opts.get("--namespace", "default") != "retail":
        raise error("NotFound", "use the workload namespace retail", 404)
    if action in ("patch", "edit", "delete", "apply", "replace"):
        if resource in ("resourcequota", "resourcequotas", "quota", "namespace", "namespaces", "ns"):
            raise error("Forbidden", "managed namespace fields and quota are reconciled by ARM; Kubernetes API edits are blocked. " + NAMESPACE_URL, 403)
        raise error("MockNotImplemented", "workload manifest editing is outside the modeled subset", 0, 2)
    w = cluster["_workload"]
    quota = cluster["_managedNamespaces"]["retail"]["defaultResourceQuota"]
    problem = f"FailedCreate: pods api-* forbidden: exceeded quota managed-quota: requests.cpu used=2, hard={quota['cpuRequest']}. See {NAMESPACE_CONCEPTS_URL}"
    if action == "scale" and resource in ("deployment", "deploy", "deployments"):
        w["replicas"] = int(opts.get("--replicas", w["replicas"]))
        reconcile(cluster)
        return "deployment.apps/api scaled\n", False
    if action == "rollout" and resource == "status":
        if w["ready"] != w["replicas"]:
            raise error("ProgressDeadlineExceeded", problem, 400)
        return 'deployment "api" successfully rolled out\n', True
    if action not in ("get", "describe"):
        raise error("MockNotImplemented", "Kubernetes operation outside the modeled subset", 0, 2)
    if resource in ("deploy", "deployment", "deployments", "deployment.apps"):
        data = {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "api", "namespace": "retail"},
                "spec": {"replicas": w["replicas"], "template": {"spec": {"containers": [{"name": "api", "resources": {"requests": {"cpu": w["cpu_request"]}}}]}}},
                "status": {"readyReplicas": w["ready"], "availableReplicas": w["ready"],
                           "conditions": [] if w["ready"] == w["replicas"] else [{"type": "ReplicaFailure", "status": "True", "reason": "FailedCreate", "message": problem}]}}
        verify = True
    elif resource in ("resourcequota", "resourcequotas", "quota"):
        data = {"kind": "ResourceQuota", "metadata": {"name": "managed-quota", "namespace": "retail", "labels": {"ManagedByARM": "true"}},
                "spec": {"hard": {"requests.cpu": quota["cpuRequest"], "limits.cpu": quota["cpuLimit"], "requests.memory": quota["memoryRequest"], "limits.memory": quota["memoryLimit"]}},
                "status": {"used": {"requests.cpu": str(w["ready"])}, "hard": {"requests.cpu": quota["cpuRequest"]}}}
        verify = False
    elif resource in ("events", "event"):
        data = {"items": [] if w["ready"] == w["replicas"] else [{"reason": "FailedCreate", "message": problem}]}
        verify = False
    elif resource in ("pods", "pod"):
        data = {"items": [{"metadata": {"name": f"api-{i}"}, "status": {"phase": "Running"}} for i in range(w["ready"])]}
        verify = True
    elif resource in ("ns", "namespace", "namespaces"):
        data = {"metadata": {"name": "retail", "labels": {"ManagedByARM": "true"}}}
        verify = False
    elif resource in ("limitrange", "limitranges", "limits"):
        data, verify = {"kind": "List", "items": []}, False
    elif resource in ("networkpolicy", "networkpolicies", "netpol"):
        policies = []
        settings = cluster["_managedNamespaces"]["retail"]["defaultNetworkPolicy"]
        for direction in ("ingress", "egress"):
            mode = settings[direction]
            rules = [] if mode == "DenyAll" else [{}] if mode == "AllowAll" else [{"from" if direction == "ingress" else "to": [{"podSelector": {}}]}]
            policies.append({"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
                             "metadata": {"name": f"managed-{direction}", "namespace": "retail"},
                             "spec": {"podSelector": {}, "policyTypes": [direction.title()], direction: rules}})
        data, verify = {"kind": "List", "items": policies}, False
    else:
        raise error("MockNotImplemented", "Kubernetes resource outside the modeled subset", 0, 2)
    # JSON is also valid YAML, allowing common -o yaml inspection without a YAML dependency.
    return json.dumps(data, indent=2) + "\n", verify


def kubeconfig(cluster):
    # A deliberately unusable real endpoint; the mock kubectl uses host-owned state.
    name = cluster["name"]
    return json.dumps({"apiVersion": "v1", "kind": "Config", "current-context": name,
                       "clusters": [{"name": name, "cluster": {"server": "https://127.0.0.1:9"}}],
                       "contexts": [{"name": name, "context": {"cluster": name, "user": "benchmark"}}],
                       "users": [{"name": "benchmark", "user": {}}]}, indent=2) + "\n"


def diagnostics(scenario, state, events, command, options, error):
    cluster = scenario.get("cluster_template") or scenario["initial_state"]["clusters"][0]
    if options.get("--resource-group", cluster["resourceGroup"]) != cluster["resourceGroup"]:
        return []
    if command == "deployment group list":
        # Direct az aks SDK operations do not create an ARM template deployment.
        return []
    if scenario["name"] == "debug-version-skew":
        failure = {"code": "NodePoolMcVersionIncompatible", "message": "Requested pool version 1.34.2 is greater than control plane 1.33.5. " + VERSION_URL}
        operation = "Microsoft.ContainerService/managedClusters/agentPools/write"
        resource_id = cluster["id"] + "/agentPools/apps"
    elif scenario["name"] == "debug-automatic-provider":
        failure = {"code": "MissingSubscriptionRegistration", "message": "The subscription is not registered to use namespace Microsoft.PolicyInsights. " + PROVIDER_URL}
        operation = "Microsoft.ContainerService/managedClusters/write"
        resource_id = cluster["id"]
    else:
        if command == "monitor activity-log list":
            return []
        raise error("MockNotImplemented", "operation history is not available for this scenario", 0, 2)
    if command == "aks operation show-latest":
        if options.get("--name") != cluster["name"] or not any(c["id"] == cluster["id"] for c in state["clusters"]):
            raise error("ResourceNotFound", "managed cluster not found", 404)
        mutations = {"aks create", "aks update", "aks upgrade", "aks nodepool upgrade"}
        recent = next((e for e in reversed(events) if e["command"] in mutations and e["category"] == "azure"), None)
        succeeded = recent is not None and recent["exit_code"] == 0
        return {"id": cluster["id"] + "/operations/benchmark", "status": "Succeeded" if succeeded else "Failed", "error": None if succeeded else failure}
    if options.get("--status", "Failed").lower() != "failed":
        return []
    if options.get("--resource-id") and not resource_id.startswith(options["--resource-id"]):
        return []
    record = {"eventTimestamp": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
              "resourceId": resource_id, "resourceGroupName": cluster["resourceGroup"],
              "operationName": {"value": operation, "localizedValue": operation},
              "status": {"value": "Failed", "localizedValue": "Failed"},
              "subStatus": {"value": "BadRequest", "localizedValue": "Bad Request"},
              "properties": {"statusMessage": json.dumps({"status": "Failed", "error": failure})}}
    return [record][:int(options.get("--max-events", 1))]


def oracle_commands(scenario):
    if scenario["name"] == "debug-automatic-provider":
        return [["provider", "register", "--namespace", "Microsoft.PolicyInsights", "--wait"],
                *automatic.oracle_commands({**scenario, "name": "automatic-create"})]
    c = scenario["state"]["clusters"][0]
    cluster = ["-g", c["resourceGroup"], "-n", c["name"]]
    pool = ["-g", c["resourceGroup"], "--cluster-name", c["name"], "-n", "apps"]
    if scenario["name"] == "debug-version-skew":
        return [["aks", "get-upgrades", *cluster], ["aks", "upgrade", *cluster, "--kubernetes-version", "1.34.2", "--control-plane-only", "--yes"],
                ["aks", "nodepool", "upgrade", *pool, "--kubernetes-version", "1.34.2"], ["aks", "nodepool", "show", *pool]]
    return [["aks", "namespace", "show", "-g", c["resourceGroup"], "--cluster-name", c["name"], "-n", "retail"],
            ["aks", "namespace", "update", "-g", c["resourceGroup"], "--cluster-name", c["name"], "-n", "retail", "--cpu-request", "4000m"],
            {"tool": "kubectl", "argv": ["get", "deployment", "api", "-n", "retail", "-o", "json"]}]
