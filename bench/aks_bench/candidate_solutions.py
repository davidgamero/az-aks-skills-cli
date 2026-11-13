"""Reference operations for simulator validation, never supplied to agents."""

import copy
import json

from .candidate_fixtures import obj


def kube(*argv, files=None, expect_exit=0):
    result = {"tool": "kubectl", "argv": list(argv)}
    if files: result["files"] = files
    if expect_exit: result["expect_exit"] = expect_exit
    return result


def patch(kind, name, value, namespace="retail"):
    return kube("patch", f"{kind}/{name}", "-n", namespace, "--type", "strategic", "-p", json.dumps(value))


def apply(value):
    return kube("apply", "-f", "/work/desired.json", files={"/work/desired.json": json.dumps(value)})


def commands(s):
    name, x = s["name"], s["context"]
    base = ["-g", x["resource_group"], "--cluster-name", x["cluster"]]
    cluster = ["-g", x["resource_group"], "-n", x["cluster"]]
    ns = [*base, "-n", "retail"]
    get_workload = kube("get", "deployment/api", "-n", "retail", "-o", "json")
    rollout = kube("rollout", "status", "deployment/api", "-n", "retail", "--timeout=30s")
    probe = kube("exec", "deployment/api", "-n", "retail", "--", "/app/probe", "--all")
    if name == "managed-namespace-adopt-identical":
        return [["aks", "namespace", "add", *ns, "--adoption-policy", "IfIdentical", "--delete-policy", "Keep",
                 "--cpu-request", "4000m", "--cpu-limit", "8000m", "--memory-request", "2Gi", "--memory-limit", "4Gi",
                 "--ingress-policy", "AllowSameNamespace", "--egress-policy", "AllowAll", "--labels", "team=retail", "--annotations", "owner=platform"],
                ["aks", "namespace", "show", *ns], get_workload]
    if name == "managed-namespace-detach-keep":
        return [["aks", "namespace", "update", *ns, "--delete-policy", "Keep"], ["aks", "namespace", "delete", *ns, "--yes"],
                {"tool": "az", "argv": ["aks", "namespace", "show", *ns], "expect_exit": 1},
                kube("get", "namespace/retail", "-o", "json"), get_workload, kube("get", "pvc/data", "-n", "retail", "-o", "json")]
    if name == "managed-namespace-rbac-plane":
        return [["role", "assignment", "create", "--assignee-object-id", x["developer_object_id"], "--assignee-principal-type", "User",
                 "--role", "Azure Kubernetes Service RBAC Reader", "--scope", x["approved_namespace_scope"]],
                kube("auth", "can-i", "list", "pods", "-n", "retail", "--as", x["developer_object_id"]),
                kube("auth", "can-i", "get", "secrets", "-n", "retail", "--as", x["developer_object_id"], expect_exit=1),
                kube("auth", "can-i", "list", "pods", "-n", "other", "--as", x["developer_object_id"], expect_exit=1)]
    if name == "managed-namespace-selective-ingress":
        policy = obj("NetworkPolicy", "allow-approved-ingress", "retail", {"podSelector": {"matchLabels": {"app": "api"}}, "policyTypes": ["Ingress"],
                "ingress": [{"from": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "ingress"}}}], "ports": [{"protocol": "TCP", "port": 8080}]}]})
        return [apply(policy), kube("exec", "controller-0", "-n", "ingress", "--", "curl", "http://api.retail.svc.cluster.local:8080/health"),
                kube("exec", "probe", "-n", "other", "--", "curl", "http://api.retail.svc.cluster.local:8080/health", expect_exit=28)]
    if name == "acr-abac-pull-repair":
        return [["role", "assignment", "create", "--assignee-object-id", "kubelet-principal", "--assignee-principal-type", "ServicePrincipal",
                 "--role", "Container Registry Repository Reader", "--scope", x["registry_id"], "--condition-version", "2.0",
                 "--condition", "@Resource[Microsoft.ContainerRegistry/registries/repositories:name] StringEquals 'team/api'"], rollout]
    if name in ("acr-private-data-endpoint", "api-connectivity-stage-repair"):
        change = ["network", "nsg", "rule", "update", "-g", "network-rg", "--nsg-name", "app-network", "-n", "required-path", "--access", "Allow"]
        return [change, rollout] if name.startswith("acr") else [change, kube("get", "--raw=/version"), kube("logs", "deployment/api", "-n", "retail")]
    if name == "workload-federation-versus-rbac":
        issuer = s["state"]["clusters"][0]["oidcIssuerProfile"]["issuerUrl"]
        return [["identity", "federated-credential", "update", "-g", x["resource_group"], "--identity-name", "app-id", "-n", "app-fic",
                 "--issuer", issuer, "--subject", "system:serviceaccount:retail:app-sa", "--audiences", "api://AzureADTokenExchange"], probe]
    if name == "identity-binding-mixed-audiences":
        value = {"spec": {"template": {"spec": {"volumes": [{"name": "direct-token", "projected": {"sources": [{"serviceAccountToken": {"path": "token", "audience": "api://AzureADTokenExchange"}}]}}],
                 "containers": [{"name": "api", "volumeMounts": [{"name": "direct-token", "mountPath": "/var/run/direct", "readOnly": True}],
                                 "env": [{"name": "DIRECT_FIC_TOKEN_FILE", "value": "/var/run/direct/token"}]}]}}}}
        return [patch("deployment", "api", value), probe]
    if name == "nap-capacity-control-plane":
        return [patch("nodepool", "workers", {"spec": {"limits": {"cpu": "8"}}}), get_workload, kube("get", "nodeclaims", "-o", "json")]
    if name == "nap-image-pickup-versus-disruption":
        return [["aks", "maintenanceconfiguration", "add", *base, "-n", "aksManagedNodeOSUpgradeSchedule", "--schedule-type", "Weekly",
                 "--day-of-week", "Sunday", "--interval-weeks", "1", "--duration", "4", "--start-time", "01:00", "--utc-offset", "+00:00"],
                ["aks", "maintenanceconfiguration", "show", *base, "-n", "aksManagedNodeOSUpgradeSchedule"],
                kube("get", "nodeclaims", "-o", "json"), kube("get", "pdb/api-pdb", "-n", "retail", "-o", "json")]
    if name == "automatic-admission-mutation-quota":
        value = {"spec": {"template": {"spec": {"containers": [{"name": "api", "resources": x["approved_resources"]}]}}}}
        return [patch("deployment", "api", value), get_workload, kube("get", "pods", "-n", "retail", "-o", "json")]
    if name == "pdb-preserving-upgrade":
        return [kube("scale", "deployment/api", "-n", "retail", "--replicas", "3"), rollout,
                kube("get", "pdb/api-pdb", "-n", "retail", "-o", "json"),
                ["aks", "nodepool", "upgrade", *base, "-n", "apps", "--kubernetes-version", "1.34.2"],
                kube("scale", "deployment/api", "-n", "retail", "--replicas", "2"),
                ["aks", "nodepool", "show", *base, "-n", "apps"], get_workload, kube("get", "pdb/api-pdb", "-n", "retail", "-o", "json")]
    if name == "csi-secret-sync-alias":
        value = {"spec": {"secretObjects": [{"secretName": "app-secret", "type": "Opaque", "data": [{"key": "config", "objectName": "app-key"}]}]}}
        return [patch("secretproviderclass", "app-secrets", value), kube("get", "secret/app-secret", "-n", "retail", "-o", "json"), probe]
    if name == "csi-rotation-consumption-mode":
        return [kube("rollout", "restart", "deployment/api", "-n", "retail"), probe]
    if name == "overlay-cidr-exhaustion":
        return [["aks", "update", *cluster, "--pod-cidr", "10.244.0.0/20"], ["aks", "show", *cluster], kube("get", "nodes", "-o", "json"), kube("get", "nnc", "-A", "-o", "json")]
    if name == "gateway-api-publish":
        route = obj("HTTPRoute", "api-route", "retail", {"parentRefs": [{"name": "existing-gw"}], "hostnames": [x["approved_hostname"]],
                    "rules": [{"matches": [{"path": {"type": "PathPrefix", "value": x["approved_path"]}}], "backendRefs": [{"name": "api", "port": 8080}]}]})
        return [apply(route), kube("get", "gateway/existing-gw", "-n", "retail", "-o", "json"), kube("get", "httproute/api-route", "-n", "retail", "-o", "json"),
                {"tool": "curl", "argv": ["-H", "Host:api.example.test", "http://198.51.100.40/api"]}]
    raise ValueError(name)


def execute(simulator, command):
    if isinstance(command, dict):
        return simulator.call(command["argv"], tool=command.get("tool", "az"), files=command.get("files"), stdin=command.get("stdin"))
    return simulator.call(command)
