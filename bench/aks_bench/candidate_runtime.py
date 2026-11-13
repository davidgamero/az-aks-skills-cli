"""Bounded Azure/Kubernetes resource model. Never executes host or remote commands."""

import copy
import ast
import fnmatch
import ipaddress
import json
import re
import shlex
from decimal import Decimal
from pathlib import PurePosixPath
from urllib.parse import urlparse

import jmespath
import yaml

from .candidate_fixtures import key, obj, put


class WorldError(Exception):
    def __init__(self, code, message, status=400, exit_code=1, tags=()):
        super().__init__(message)
        self.code, self.status, self.exit_code, self.tags = code, status, exit_code, tags


ALIASES = {"ns": "namespace", "namespaces": "namespace", "po": "pod", "pods": "pod", "deploy": "deployment",
           "deployments": "deployment", "svc": "service", "services": "service", "pvc": "persistentvolumeclaim",
           "persistentvolumeclaims": "persistentvolumeclaim", "pdb": "poddisruptionbudget", "poddisruptionbudgets": "poddisruptionbudget",
           "resourcequotas": "resourcequota", "quota": "resourcequota", "netpol": "networkpolicy", "networkpolicies": "networkpolicy",
           "sa": "serviceaccount", "serviceaccounts": "serviceaccount", "secrets": "secret", "nodes": "node",
           "nodepools": "nodepool", "nodeclaims": "nodeclaim", "aksnodeclasses": "aksnodeclass", "nnc": "nodenetworkconfig",
           "nodenetworkconfigs": "nodenetworkconfig", "secretproviderclasses": "secretproviderclass",
           "gateways": "gateway", "httproutes": "httproute", "gatewayclasses": "gatewayclass", "rs": "replicaset",
           "replicasets": "replicaset", "events": "event", "limitranges": "limitrange", "cm": "configmap", "configmaps": "configmap"}
ALIASES.update({"secretproviderclasspodstatuses": "secretproviderclasspodstatus", "daemonsets": "daemonset", "endpoints": "endpoints", "ep": "endpoints"})
CLUSTER_KINDS = {"namespace", "node", "nodepool", "nodeclaim", "aksnodeclass", "gatewayclass", "clusterrole", "clusterrolebinding", "customresourcedefinition"}
BOOLS = {"--help", "-h", "--yes", "-y", "--no-wait", "--wait", "--overwrite", "--overwrite-existing", "--all-namespaces", "-A",
         "--include-inherited", "--all", "--only-show-errors", "--admin", "--enable-oidc-issuer", "--enable-workload-identity",
         "--enable-gateway-api", "--enable-app-routing-istio", "--enable-acns", "--enable-secret-rotation", "--force", "--ignore-not-found"}
BOOLS.update({"--control-plane-only", "--version", "--rm", "-i", "-t", "--stdin", "--tty", "--list", "--show-labels", "--ignore-errors"})
MULTI = {"--labels", "--annotations", "--tags", "--audiences", "--excluded-ns", "--set"}


def parse(argv, tool="az"):
    words, opts, tail = [], {}, []
    aliases = {"-g": "--resource-group", "-n": "--name" if tool == "az" else "--namespace", "-o": "--output", "-f": "--file", "--filename": "--file", "-p": "--patch", "-l": "--location" if tool == "az" else "--selector"}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--":
            tail = argv[i + 1:]
            break
        if arg.startswith("-") and arg != "-":
            k, eq, value = arg.partition("=")
            k = aliases.get(k, k)
            if eq:
                opts[k] = value
            elif k in BOOLS:
                opts[k] = True
            else:
                i += 1
                if i == len(argv):
                    raise WorldError("ArgumentError", f"expected value for {k}", 0, 2)
                values = [argv[i]]
                if k in MULTI:
                    while i + 1 < len(argv) and not argv[i + 1].startswith("-"):
                        i += 1
                        values.append(argv[i])
                opts[k] = values if k in MULTI else values[0]
        else:
            words.append(arg)
        i += 1
    return words, opts, tail


def quantity(value):
    text = str(value)
    for suffix, factor in (("Gi", 1024**3), ("Mi", 1024**2), ("Ki", 1024), ("m", Decimal("0.001"))):
        if text.endswith(suffix):
            return Decimal(text[:-len(suffix)]) * factor
    return Decimal(text)


def merge(old, patch, strategic=False):
    if not isinstance(patch, dict):
        if strategic and isinstance(old, list) and isinstance(patch, list) and all(isinstance(v, dict) and "name" in v for v in old + patch):
            result = copy.deepcopy(old)
            for value in patch:
                index = next((i for i, v in enumerate(result) if v["name"] == value["name"]), None)
                if value.get("$patch") == "delete":
                    if index is not None: result.pop(index)
                    continue
                if index is None:
                    result.append(copy.deepcopy(value))
                else:
                    result[index] = merge(result[index], value, True)
            return result
        return copy.deepcopy(patch)
    result = copy.deepcopy(old) if isinstance(old, dict) else {}
    for k, v in patch.items():
        if v is None:
            result.pop(k, None)
        else:
            result[k] = merge(result.get(k), v, strategic)
    return result


def json_patch(document, operations):
    result = copy.deepcopy(document)
    for operation in operations:
        parts = [p.replace("~1", "/").replace("~0", "~") for p in operation["path"].strip("/").split("/")]
        node = result
        for part in parts[:-1]:
            node = node[int(part)] if isinstance(node, list) else node[part]
        field = parts[-1]
        if operation["op"] == "remove":
            if isinstance(node, list): node.pop(int(field))
            else: node.pop(field)
        elif operation["op"] in ("add", "replace"):
            if isinstance(node, list):
                if field == "-": node.append(copy.deepcopy(operation["value"]))
                elif operation["op"] == "add": node.insert(int(field), copy.deepcopy(operation["value"]))
                else: node[int(field)] = copy.deepcopy(operation["value"])
            else: node[field] = copy.deepcopy(operation["value"])
        elif operation["op"] == "test":
            if node[field] != operation["value"]: raise WorldError("Conflict", "JSON patch test failed", 409)
        else:
            raise WorldError("MockNotImplemented", "JSON patch operation outside model", 0, 2)
    return result


def kv(values):
    if isinstance(values, str): values = [values]
    return dict(v.split("=", 1) for v in (values or []))


def canonical(resource):
    value = resource.lower().split(".", 1)[0]
    return ALIASES.get(value, value)


def condition_allows(expression, repository, action):
    """Bounded Azure ABAC boolean subset; no Python eval or arbitrary expressions."""
    if not expression: return True
    pattern = r"@Resource\[Microsoft\.ContainerRegistry/registries/repositories:name\]\s+StringEquals\s+'([^']*)'"
    text = re.sub(pattern, lambda m: str(repository == m[1]), expression, flags=re.I)
    text = re.sub(r"ActionMatches\s*\{\s*'([^']*)'\s*\}", lambda m: str(fnmatch.fnmatchcase(action, m[1])), text, flags=re.I)
    text = re.sub(r"\bAND\b", "and", text, flags=re.I)
    text = re.sub(r"\bOR\b", "or", text, flags=re.I).replace("!", " not ").strip()
    try: tree = ast.parse(text, mode="eval")
    except SyntaxError as error: raise WorldError("MockNotImplemented", "ABAC condition outside modeled StringEquals/ActionMatches subset", 0, 2) from error
    def evaluate(node):
        if isinstance(node, ast.Expression): return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, bool): return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not): return not evaluate(node.operand)
        if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            values = [evaluate(v) for v in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)
        raise WorldError("MockNotImplemented", "ABAC expression outside modeled subset", 0, 2)
    return evaluate(tree)


def jsonpath(expression, value):
    expression = expression.removeprefix("jsonpath=").strip("'\"")
    def part(text, row):
        if text.startswith('"'):
            return json.loads(text)
        found = jmespath.search(text.lstrip("."), row)
        if isinstance(found, list): return " ".join(str(v) for v in found)
        return "" if found is None else str(found).lower() if isinstance(found, bool) else str(found)
    ranged = re.fullmatch(r"\{range (.+?)\}(.*)\{end\}", expression, re.S)
    if ranged:
        return "".join("".join(part(p, row) for p in re.findall(r"\{(.*?)\}", ranged[2])) for row in jmespath.search(ranged[1].lstrip("."), value))
    return "".join(part(p, value) for p in re.findall(r"\{(.*?)\}", expression))


class World:
    def __init__(self, scenario, state):
        self.scenario, self.state = scenario, state
        self.name = scenario["name"]
        self.context = scenario["context"]

    @property
    def cluster(self): return self.state["clusters"][0]

    @property
    def w(self): return self.cluster["_world"]

    def get(self, kind, name, namespace="retail"):
        kind = canonical(kind)
        namespace = "" if kind in CLUSTER_KINDS else namespace
        return self.w["resources"].get(key(kind, namespace, name))

    def observe(self, tags):
        for tag in tags:
            self.w["observations"][tag] = self.w["generation"]

    def role(self, principal, role, scope):
        return any(r["principalId"] == principal and r["roleDefinitionName"].lower() == role.lower() and r["scope"].rstrip("/") == scope.rstrip("/") for r in self.w["roles"])

    def pull_ok(self):
        registry = self.w["registry"]
        matches = [r for r in self.w["roles"] if r["principalId"] == "kubelet-principal" and r["scope"] == registry["id"]]
        if registry["roleAssignmentMode"] == "AbacRepositoryPermissions":
            authorized = any(r["roleDefinitionName"] == "Container Registry Repository Reader" and
                             all(condition_allows(r.get("condition"), self.context["repository"], a) for a in
                                 ("Microsoft.ContainerRegistry/registries/repositories/content/read", "Microsoft.ContainerRegistry/registries/repositories/metadata/read")) for r in matches)
        else:
            authorized = any(r["roleDefinitionName"] == "AcrPull" for r in matches)
        network = self.name != "acr-private-data-endpoint" or self.w["nsg"]["securityRules"][0]["access"] == "Allow"
        return authorized and network

    def workload_access(self, flow="direct"):
        deployment = self.get("deployment", "api")
        if not deployment: return False
        spec = deployment["spec"]["template"]["spec"]
        sa = self.get("serviceaccount", spec.get("serviceAccountName", "default"))
        principal_ok = sa is not None and sa["metadata"].get("annotations", {}).get("azure.workload.identity/client-id") == "app-client"
        labels_ok = deployment["spec"]["template"]["metadata"].get("labels", {}).get("azure.workload.identity/use") == "true"
        role_ok = self.role("app-principal", "Key Vault Secrets User", self.w["vault"]["id"])
        if flow == "binding":
            binding_volume = next((v for v in spec.get("volumes", []) if v["name"] == "binding-token"), {})
            audience_ok = any(s.get("serviceAccountToken", {}).get("audience") == "api://AKSIdentityBinding" for s in binding_volume.get("projected", {}).get("sources", []))
            return principal_ok and labels_ok and role_ok and audience_ok and self.w.get("identity_binding", {}).get("provisioningState") == "Succeeded" and self.w.get("sdk", {}).get("enable_azure_proxy") is True
        fic_ok = any(f["issuer"] == self.cluster["oidcIssuerProfile"]["issuerUrl"] and
                     f["subject"] == "system:serviceaccount:retail:app-sa" and
                     f["audiences"] == ["api://AzureADTokenExchange"] for f in self.w["federated_credentials"])
        if self.name == "identity-binding-mixed-audiences":
            container = spec["containers"][0]
            path = next((e.get("value") for e in container.get("env", []) if e["name"] == "DIRECT_FIC_TOKEN_FILE"), "")
            audience = None
            for volume in spec.get("volumes", []):
                mount = next((m for m in container.get("volumeMounts", []) if m["name"] == volume["name"]), None)
                if mount:
                    for source in volume.get("projected", {}).get("sources", []):
                        token = source.get("serviceAccountToken", {})
                        if str(PurePosixPath(mount["mountPath"]) / token.get("path", "")) == path:
                            audience = token.get("audience")
            fic_ok = fic_ok and audience == "api://AzureADTokenExchange"
        return principal_ok and labels_ok and role_ok and fic_ok

    def namespace_access(self, verb, resource, namespace, principal):
        roles = [r for r in self.w["roles"] if r["principalId"] == principal]
        for r in roles:
            scope_ok = r["scope"] == self.cluster["id"] or r["scope"] == self.cluster["id"] + f"/managedNamespaces/{namespace}"
            if not scope_ok: continue
            name = r["roleDefinitionName"]
            if name in ("Azure Kubernetes Service RBAC Admin", "Azure Kubernetes Service RBAC Cluster Admin", "Owner"): return True
            if name == "Azure Kubernetes Service RBAC Writer": return True
            if name == "Azure Kubernetes Service RBAC Reader" and verb in ("get", "list", "watch") and resource not in ("secret", "secrets"): return True
        return False

    def traffic(self, source_namespace):
        destination_labels = {"app": "api"}
        namespace = self.get("namespace", source_namespace, "")
        source_labels = namespace["metadata"].get("labels", {}) if namespace else {}
        policies = [r for r in self.w["resources"].values() if r["kind"] == "NetworkPolicy" and r["metadata"].get("namespace") == "retail"
                    and all(destination_labels.get(k) == v for k,v in r.get("spec", {}).get("podSelector", {}).get("matchLabels", {}).items())
                    and "Ingress" in r["spec"].get("policyTypes", ["Ingress"])]
        if not policies: return True
        for policy in policies:
            for rule in policy["spec"].get("ingress", []):
                ports = rule.get("ports", [])
                if ports and not any(str(p.get("port")) == "8080" for p in ports): continue
                if "from" not in rule: return True
                for peer in rule["from"]:
                    if not peer: return True
                    ns_selector = peer.get("namespaceSelector")
                    ns_match = source_namespace == "retail" if ns_selector is None else all(source_labels.get(k) == v for k,v in ns_selector.get("matchLabels", {}).items())
                    pod_labels = {"app": "ingress" if source_namespace == "ingress" else "api" if source_namespace == "retail" else "probe"}
                    pod_match = all(pod_labels.get(k) == v for k,v in peer.get("podSelector", {}).get("matchLabels", {}).items())
                    if ns_match and pod_match: return True
        return False

    def reconcile(self):
        w = self.w
        deployment = self.get("deployment", "api")
        if not deployment: return
        desired = deployment["spec"].get("replicas", 1)
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        effective = copy.deepcopy(container.get("resources", {}))
        if self.name == "automatic-admission-mutation-quota" and not effective:
            effective = {"requests": {"cpu": "500m", "memory": "2Gi"}, "limits": {"cpu": "500m", "memory": "2Gi"}}
        ready = desired
        reason = ""
        if self.name in ("acr-abac-pull-repair", "acr-private-data-endpoint") and not self.pull_ok():
            ready, reason = 0, "ImagePullBackOff: " + ("layer download to private data endpoint timed out" if self.name.endswith("data-endpoint") else "failed to fetch oauth token: 401 Unauthorized")
        if self.name == "nap-capacity-control-plane":
            pool = self.get("nodepool", "workers", "")
            if pool is None or (quantity(pool["spec"].get("limits", {}).get("cpu", "0")) < 8 and self.get("nodeclaim", "workers-2", "") is None):
                ready, reason = 2, "FailedScheduling: NodePool workers resource limit reached; no new NodeClaim"
            else:
                claim = self.get("nodeclaim", "workers-2", "") or obj("NodeClaim", "workers-2", "", {"nodeClassRef": {"name": "default"}})
                claim["status"] = {"conditions": [{"type": "Ready", "status": "True"}], "capacity": {"cpu": "4"}}
                put(w, claim)
                pool["status"] = {"resources": {"cpu": "8"}, "conditions": [{"type": "Ready", "status": "True"}]}
                node = self.get("node", "workers-2", "") or obj("Node", "workers-2", "", {"podCIDR": "10.244.21.0/24"})
                node["metadata"]["labels"] = {"karpenter.sh/nodepool": "workers"}
                node["status"] = {"conditions": [{"type": "Ready", "status": "True"}], "capacity": {"cpu": "4"}}
                put(w, node)
        if self.name == "automatic-admission-mutation-quota":
            quota_resource = self.get("resourcequota", "managed-quota")
            if not quota_resource: raise WorldError("InvalidState", "required managed quota missing")
            quota = quota_resource["spec"]["hard"]
            ready = min(desired, int(quantity(quota["requests.cpu"]) / quantity(effective["requests"]["cpu"])),
                        int(quantity(quota["requests.memory"]) / quantity(effective["requests"]["memory"])))
            if ready < desired: reason = "FailedCreate: effective admitted resource requests exceed namespace quota"
        if self.name == "csi-secret-sync-alias":
            spc = self.get("secretproviderclass", "app-secrets")
            spec = deployment["spec"]["template"]["spec"]
            mounted = desired > 0 and any(v.get("csi", {}).get("volumeAttributes", {}).get("secretProviderClass") == "app-secrets" and
                any(m.get("name") == v.get("name") for m in container.get("volumeMounts", [])) for v in spec.get("volumes", []))
            aliases = []
            if spc:
                objects = yaml.safe_load(spc["spec"]["parameters"].get("objects", "{}")) or {}
                for raw in objects.get("array", []):
                    entry = yaml.safe_load(raw) if isinstance(raw, str) else raw
                    aliases.append(entry.get("objectAlias", entry.get("objectName")))
                sync = spc["spec"].get("secretObjects", [])
                if mounted and any(o.get("secretName") == "app-secret" and any(d.get("objectName") in aliases and d.get("key") == "config" for d in o.get("data", [])) for o in sync):
                    secret = self.get("secret", "app-secret") or obj("Secret", "app-secret", "retail", type="Opaque")
                    secret["data"] = {"config": "c3ludGhldGljLXZlcnNpb24tMg=="}
                    secret["metadata"]["annotations"] = {"source-version": "version-2", "managed-by": "secrets-store-csi"}
                    put(w, secret)
            if not self.get("secret", "app-secret"):
                ready, reason = 0, "CreateContainerConfigError: app-secret not found; CSI mount succeeds but secretObjects mapping does not resolve"
        deployment["status"] = {"replicas": desired, "readyReplicas": ready, "availableReplicas": ready,
                                 "conditions": [{"type": "Available", "status": "True" if ready == desired else "False", "message": reason}]}
        if self.name == "pdb-preserving-upgrade":
            w["minimum_ready_seen"] = min(w["minimum_ready_seen"], ready)
            if ready < 2: w["violations"].append("availability-floor-breached")
            if desired > self.context["approved_temporary_replicas"]: w["violations"].append("temporary-capacity-exceeded")
        pdb = self.get("poddisruptionbudget", "api-pdb")
        if pdb:
            minimum = pdb["spec"].get("minAvailable", desired - int(pdb["spec"].get("maxUnavailable", 0)))
            if isinstance(minimum, str) and minimum.endswith("%"):
                import math
                minimum = math.ceil(desired * float(minimum[:-1]) / 100)
            pdb["status"] = {"currentHealthy": ready, "desiredHealthy": minimum, "disruptionsAllowed": max(0, ready - int(minimum))}
        pod_spec = copy.deepcopy(deployment["spec"]["template"]["spec"])
        pod_spec["containers"][0]["resources"] = effective
        admitted = ready if self.name == "automatic-admission-mutation-quota" else desired
        for existing in list(w["resources"].values()):
            if existing["kind"] == "Pod" and existing["metadata"].get("namespace") == "retail" and re.fullmatch(r"api-\d+", existing["metadata"]["name"]):
                if int(existing["metadata"]["name"].split("-")[-1]) >= admitted:
                    w["resources"].pop(key("pod", "retail", existing["metadata"]["name"]))
        for index in range(admitted):
            healthy = index < ready
            pod = self.get("pod", f"api-{index}") or obj("Pod", f"api-{index}")
            pod.update(spec=copy.deepcopy(pod_spec), status={"phase": "Running" if healthy else "Pending", "conditions": [{"type": "Ready", "status": "True" if healthy else "False"}],
                        "containerStatuses": [{"name": "api", "ready": healthy, "image": container["image"], "imageID": "sha256:intended-image" if healthy else "", "state": {"running": {}} if healthy else {"waiting": {"reason": reason}}}]})
            pod["metadata"]["labels"] = copy.deepcopy(deployment["spec"]["template"]["metadata"].get("labels", {}))
            put(w, pod)
        for ns, name in (("ingress", "controller-0"), ("other", "probe")):
            if not self.get("pod", name, ns):
                probe = obj("Pod", name, ns, {"containers": [{"name": "probe", "image": "curlimages/curl:8.10.1"}]}, status={"phase": "Running"})
                probe["metadata"]["labels"] = {"app": "ingress" if ns == "ingress" else "probe"}
                put(w, probe)
        for resource in list(w["resources"].values()):
            if resource["kind"] != "Pod" or re.fullmatch(r"api-\d+", resource["metadata"]["name"]): continue
            containers = resource.get("spec", {}).get("containers", [])
            if containers and containers[0].get("image", "").startswith(w["registry"]["loginServer"]+"/"):
                pulled = containers[0]["image"] == self.context["approved_image"] and self.pull_ok()
                resource["status"] = {"phase": "Running" if pulled else "Pending", "conditions": [{"type": "Ready", "status": "True" if pulled else "False"}],
                    "containerStatuses": [{"name": containers[0]["name"], "ready": pulled, "image": containers[0]["image"], "imageID": "sha256:intended-image" if pulled else "", "state": {"running": {}} if pulled else {"waiting": {"reason": "ImagePullBackOff"}}}]}
        quota_resource = self.get("resourcequota", "managed-quota")
        if quota_resource:
            quota_resource["status"] = {"hard": copy.deepcopy(quota_resource["spec"]["hard"]),
                "used": {"requests.cpu": str(admitted * quantity(effective.get("requests", {}).get("cpu", "0"))),
                         "requests.memory": str(admitted * quantity(effective.get("requests", {}).get("memory", "0")))}}
        if self.name == "overlay-cidr-exhaustion":
            network = ipaddress.ip_network(self.cluster["networkProfile"]["podCidr"])
            nodes = [r for r in w["resources"].values() if r["kind"] == "Node"]
            capacity = 2 ** (24 - network.prefixlen)
            for i, node in enumerate(nodes):
                node["status"]["conditions"] = [{"type": "Ready", "status": "True" if i < capacity else "False"}]
                put(w, obj("NodeNetworkConfig", node["metadata"]["name"], "kube-system", status={"networkContainers": [{"subnetAddressSpace": str(network)}]}))
        for gateway in [r for r in w["resources"].values() if r["kind"] == "Gateway"]:
            valid = gateway["spec"].get("gatewayClassName") == "approuting-istio" and self.get("gatewayclass", "approuting-istio", "") is not None and any(l.get("protocol") == "HTTP" and l.get("port") == 80 for l in gateway["spec"].get("listeners", []))
            gateway["status"] = {"addresses": [{"type": "IPAddress", "value": "198.51.100.40"}], "conditions": [{"type": "Programmed", "status": "True" if valid else "False"}]}
        for route in [r for r in w["resources"].values() if r["kind"] == "HTTPRoute"]:
            ns = route["metadata"].get("namespace", "retail")
            accepted = any(self.route_listeners(route, p) for p in route["spec"].get("parentRefs", []))
            resolved = all(self.backend_ready(b, ns) for rule in route["spec"].get("rules", []) for b in rule.get("backendRefs", []))
            route["status"] = {"parents": [{"conditions": [{"type": "Accepted", "status": "True" if accepted else "False"}, {"type": "ResolvedRefs", "status": "True" if resolved else "False"}]}]}

    def route_listeners(self, route, parent):
        ns = route["metadata"].get("namespace", "retail")
        gateway = self.get("gateway", parent.get("name"), parent.get("namespace", ns))
        if not gateway or gateway["spec"].get("gatewayClassName") != "approuting-istio": return []
        if not any(c.get("type") == "Programmed" and c.get("status") == "True" for c in gateway.get("status", {}).get("conditions", [])): return []
        if gateway["metadata"].get("namespace") != ns: return []  # Cross-namespace attachment is outside this fixture.
        return [l for l in gateway["spec"].get("listeners", []) if l.get("protocol") == "HTTP" and l.get("port") == 80
                and (not parent.get("sectionName") or l.get("name") == parent["sectionName"])]

    def backend_ready(self, backend, namespace):
        if backend.get("kind", "Service") != "Service" or backend.get("namespace", namespace) != namespace: return False
        service = self.get("service", backend.get("name"), namespace)
        if not service or not any(p.get("port") == backend.get("port") for p in service["spec"].get("ports", [])): return False
        selector = service["spec"].get("selector", {})
        return bool(selector) and any(r["kind"] == "Pod" and r["metadata"].get("namespace") == namespace and
            all(r["metadata"].get("labels", {}).get(k) == v for k,v in selector.items()) and
            any(c.get("type") == "Ready" and c.get("status") == "True" for c in r.get("status", {}).get("conditions", [])) for r in self.w["resources"].values())

    def apply(self, resource):
        if not isinstance(resource, dict) or "kind" not in resource or "metadata" not in resource:
            raise WorldError("InvalidManifest", "resource requires kind and metadata")
        if resource["kind"] == "List":
            return [self.apply(item) for item in resource.get("items", [])]
        resource = copy.deepcopy(resource)
        kind = canonical(resource["kind"])
        if kind == "networkpolicy":
            # Unsupported semantics must invalidate coverage rather than grant access.
            text = json.dumps(resource.get("spec", {}))
            if '"matchExpressions"' in text or '"ipBlock"' in text:
                raise WorldError("MockNotImplemented", "policy expressions/IP blocks outside primary fixture", 0, 2)
        m = resource["metadata"]
        ns = "" if kind in CLUSTER_KINDS else m.setdefault("namespace", "retail")
        old = self.get(kind, m["name"], ns)
        if (kind == "namespace" and m["name"] in self.w["managed_namespaces"]) or (ns in self.w["managed_namespaces"] and ((kind == "resourcequota" and m["name"] == "managed-quota") or (kind == "networkpolicy" and m["name"] == "managed-ingress"))):
            raise WorldError("Forbidden", "ARM-managed fields must be updated through az aks namespace", 403)
        resource.pop("status", None)
        if old and "status" in old: resource["status"] = copy.deepcopy(old["status"])
        if old:
            m["uid"] = old["metadata"]["uid"]
        else:
            m["uid"] = f"new-{kind}-{self.w['generation']}-{m['name']}"
        if kind == "secret": self.w["violations"].append("manual-secret-write")
        if kind == "poddisruptionbudget" and self.name in ("pdb-preserving-upgrade", "nap-image-pickup-versus-disruption") and resource.get("spec") != self.scenario["expected"]["pdb"]["spec"]:
            self.w["violations"].append("pdb-changed")
        if kind == "nodepool" and old and ("replicas" in old["spec"]) != ("replicas" in resource.get("spec", {})):
            raise WorldError("InvalidParameter", "NodePool static/dynamic mode cannot be switched")
        if kind == "deployment" and self.name == "csi-rotation-consumption-mode" and old and resource.get("spec", {}).get("template") != old["spec"].get("template"):
            self.w["app_secret_version"] = self.w["secret_source_version"]
        put(self.w, resource)
        return resource

    def encode(self, value, options):
        if "--query" in options: value = jmespath.search(options["--query"], value)
        output = options.get("--output", "json")
        if output == "none": return ""
        if str(output).startswith("jsonpath="): return jsonpath(output, value)
        if isinstance(value, str): return value + ("" if value.endswith("\n") else "\n")
        if output == "yaml": return yaml.safe_dump(value, sort_keys=False)
        if output == "name":
            rows = value.get("items", [value]) if isinstance(value, dict) else value
            return "".join(r["kind"].lower()+"/"+r["metadata"]["name"]+"\n" for r in rows)
        if output == "tsv":
            rows = value if isinstance(value, list) else [value]
            return "".join("\t".join(str(v).lower() if isinstance(v,bool) else str(v) for v in (r.values() if isinstance(r,dict) else [r])) + "\n" for r in rows)
        return json.dumps(value, indent=2) + "\n"

    def invoke(self, tool, argv, files=None, stdin=None):
        before_cluster = copy.deepcopy(self.cluster)
        before = copy.deepcopy(self.w)
        self.files, self.stdin = files or {}, stdin
        words, options, tail = parse(argv, tool) if tool != "curl" else (["curl"], {}, [])
        tags = []
        try:
            if tool == "az": value, tags = self.az(" ".join(words), options)
            elif tool == "kubectl": value, tags = self.kube(words, options, tail)
            elif tool == "curl": value, tags = self.probe("client", argv)
            else: raise WorldError("MockNotImplemented", f"tool {tool} is outside this model", 0, 2)
            self.reconcile()
            comparable = lambda w: {k:v for k,v in w.items() if k not in ("observations", "probe_history", "generation")}
            changed = comparable(before) != comparable(self.w) or {k:v for k,v in before_cluster.items() if not k.startswith("_")} != {k:v for k,v in self.cluster.items() if not k.startswith("_")}
            if changed: self.w["generation"] += 1
            self.observe(tags)
            return {"stdout": self.encode(value, options), "stderr": "", "exit_code": 0, "_changed": changed,
                    "_tags": tags, "_command": " ".join(words), "_status": 200}
        except WorldError as error:
            self.state["clusters"][0] = before_cluster
            self.observe(error.tags)
            return {"stdout": "", "stderr": f"ERROR: ({error.code}) {error}\n", "exit_code": error.exit_code,
                    "_changed": False, "_tags": list(error.tags), "_command": " ".join(words), "_status": error.status, "_error": error.code}
        except (ValueError, KeyError, TypeError, IndexError, ArithmeticError, yaml.YAMLError, jmespath.exceptions.JMESPathError) as error:
            self.state["clusters"][0] = before_cluster
            return {"stdout": "", "stderr": f"ERROR: (ArgumentError) {error}\n", "exit_code": 2,
                    "_changed": False, "_tags": [], "_command": " ".join(words), "_status": 400, "_error": "ArgumentError"}

    def az(self, command, o):
        c, w = self.cluster, self.w
        from .candidate_help import options_for
        unknown = set(o) - options_for(command)
        if unknown: raise WorldError("MockUnsupportedOption", "options outside modeled subset: " + ", ".join(sorted(unknown)), 0, 2)
        if command.startswith("aks "):
            cluster_name = o.get("--cluster-name") if command.startswith(("aks namespace ", "aks nodepool ", "aks maintenanceconfiguration ", "aks identity-binding ")) else o.get("--name")
            if cluster_name and cluster_name != c["name"]: raise WorldError("ResourceNotFound", "cluster not found", 404)
            if o.get("--resource-group", c["resourceGroup"]) != c["resourceGroup"]: raise WorldError("ResourceNotFound", "cluster resource group not found", 404)
        def need(option):
            if option not in o: raise WorldError("ArgumentError", f"required argument {option}", 0, 2)
            return o[option]
        if command in ("account show", "account list"):
            data = {"id": "00000000-0000-0000-0000-000000000001", "name": "Benchmark", "tenantId": "tenant", "state": "Enabled"}
            return ([data] if command.endswith("list") else data), []
        if command in ("version", "") and (command == "version" or o.get("--version")):
            return {"azure-cli": "2.86.0", "mock": True}, []
        if command in ("account set", "configure"):
            return None, []
        if command in ("group show", "group list", "group exists"):
            group = {"name": o.get("--name", c["resourceGroup"]), "location": "eastus", "properties": {"provisioningState": "Succeeded"}}
            return (True if command.endswith("exists") else [group] if command.endswith("list") else group), []
        if command in ("monitor activity-log list", "deployment group list"):
            return [], []
        if command.startswith("provider "):
            providers = ["Microsoft.ContainerService", "Microsoft.Network", "Microsoft.Compute", "Microsoft.ManagedIdentity", "Microsoft.PolicyInsights", "Microsoft.ContainerRegistry", "Microsoft.KeyVault"]
            if command.endswith("list"): return [{"namespace": p, "registrationState": "Registered"} for p in providers], []
            return {"namespace": need("--namespace"), "registrationState": "Registered"}, []
        if command in ("aks show", "aks list"):
            if o.get("--name", c["name"]) != c["name"]: raise WorldError("ResourceNotFound", "cluster not found", 404)
            data = {k:copy.deepcopy(v) for k,v in c.items() if not k.startswith("_")}
            return ([data] if command.endswith("list") else data), ["cluster", "cluster_network"]
        if command == "aks get-credentials" or command == "aks namespace get-credentials":
            if o.get("--admin") and self.name in ("managed-namespace-rbac-plane", "api-connectivity-stage-repair"):
                w["violations"].append("admin-credentials-used")
            return "Merged synthetic context " + c["name"], []
        if command == "aks check-acr":
            if not self.pull_ok():
                message = "Registry authorization failed for kubelet identity" if self.name == "acr-abac-pull-repair" else "Login endpoint reachable; data endpoint TCP 443 connection timed out"
                raise WorldError("RegistryCheckFailed", message)
            return "Registry reachable and approved image pull succeeded", ["pull"]
        if command.startswith("aks namespace "):
            return self.namespace(command.split()[-1], o)
        if command.startswith("role assignment "):
            action = command.split()[-1]
            principal = o.get("--assignee-object-id", o.get("--assignee", self.context["developer_object_id"]))
            scope = o.get("--scope")
            if scope and scope not in {c["id"], c["id"]+"/managedNamespaces/retail", w["registry"]["id"], w["vault"]["id"],
                                      "/subscriptions/00000000-0000-0000-0000-000000000001", "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/"+c["resourceGroup"]}:
                raise WorldError("ResourceNotFound", "role assignment scope does not exist in this subscription", 404)
            if action == "list":
                rows = [r for r in w["roles"] if (not ("--assignee" in o or "--assignee-object-id" in o) or r["principalId"] == principal)
                        and (scope is None or r["scope"] == scope or o.get("--include-inherited") and scope.startswith(r["scope"]))]
                return rows, ["roles"]
            if action == "create":
                role = need("--role")
                row = {"principalId": principal, "roleDefinitionName": role, "scope": need("--scope")}
                if "--condition" in o: row.update(condition=o["--condition"], conditionVersion=o.get("--condition-version", "2.0"))
                if row.get("condition"):
                    condition_allows(row["condition"], "team/api", "Microsoft.ContainerRegistry/registries/repositories/content/read")
                if self.name == "acr-abac-pull-repair" and row not in self.scenario["expected"]["roles"]:
                    from .candidate_oracles import narrow_registry_assignment
                    if not narrow_registry_assignment(row, w["registry"]["id"], self.context["repository"]):
                        w["violations"].append("registry-permission-broadened")
                if row not in w["roles"]: w["roles"].append(row)
                return row, []
            if action == "delete":
                w["roles"] = [r for r in w["roles"] if not (r["principalId"] == principal and (scope is None or r["scope"] == scope) and (not o.get("--role") or r["roleDefinitionName"] == o["--role"]))]
                return None, []
        if command == "role definition list":
            return [{"roleName": name, "name": name} for name in ("AcrPull", "Container Registry Repository Reader", "Azure Kubernetes Service RBAC Reader", "Key Vault Secrets User")], []
        if command in ("acr show", "acr list"):
            if o.get("--ids", w["registry"]["id"]) != w["registry"]["id"]: raise WorldError("ResourceNotFound", "registry not found", 404)
            return ([w["registry"]] if command.endswith("list") else w["registry"]), ["registry"]
        if command == "acr check-health":
            return {"loginEndpoint": "reachable", "dataEndpoint": "reachable" if w["nsg"]["securityRules"][0]["access"] == "Allow" else "TCP 443 timed out", "privateAddress": "10.0.2.5"}, []
        if command == "acr private-endpoint-connection list": return w["registry"]["privateEndpointConnections"], []
        if command == "acr update":
            for flag, prop in (("--public-network-enabled", "publicNetworkAccess"), ("--admin-enabled", "adminUserEnabled"), ("--role-assignment-mode", "roleAssignmentMode")):
                if flag in o: w["registry"][prop] = o[flag]
            return w["registry"], []
        if command.startswith("acr repository ") or command.startswith("acr manifest "):
            return {"name": "team/api:v2", "digest": "sha256:intended-image", "architecture": "amd64", "os": "linux"}, []
        if command in ("identity show", "identity list"):
            return (list(w["identities"].values()) if command.endswith("list") else w["identities"].get(o.get("--name", "app-id"), {})), ["identity"]
        if command.startswith("identity federated-credential "):
            action = command.split()[-1]
            rows = w["federated_credentials"]
            if action == "list": return rows, ["federation"]
            name = need("--name")
            current = next((f for f in rows if f["name"] == name), None)
            if action == "show":
                if not current: raise WorldError("ResourceNotFound", "federated credential not found", 404)
                return current, ["federation"]
            if name == "aks-identity-binding": w["violations"].append("managed-fic-modified")
            if action == "delete":
                w["federated_credentials"] = [f for f in rows if f["name"] != name]
                return None, []
            if action in ("create", "update"):
                if current is None:
                    current = {"name": name}
                    rows.append(current)
                for flag, prop in (("--issuer", "issuer"), ("--subject", "subject"), ("--audiences", "audiences"), ("--audience", "audiences")):
                    if flag in o: current[prop] = o[flag] if prop != "audiences" or isinstance(o[flag], list) else [o[flag]]
                return current, []
        if command in ("aks identity-binding show", "aks identity-binding list"):
            binding = w.get("identity_binding", {})
            return ([binding] if command.endswith("list") else binding), ["binding"]
        if command in ("keyvault show", "keyvault secret show", "keyvault secret list-versions", "keyvault secret list"):
            if command == "keyvault show": return w["vault"], []
            data = {"id": w["vault"]["properties"]["vaultUri"] + "secrets/backend-key/version-2", "name": "backend-key", "attributes": {"enabled": True}, "version": "version-2"}
            return ([data] if command.endswith(("list-versions", "list")) else data), ["secret_version"]
        if command in ("network vnet list", "network vnet show"):
            row = {"name": c["name"]+"-vnet", "resourceGroup": "network-rg", "addressSpace": {"addressPrefixes": ["10.0.0.0/16"]}, "subnets": [{"name": "nodes", "addressPrefix": "10.0.1.0/24", "networkSecurityGroup": {"id": w["nsg"]["id"]}}]}
            return ([row] if command.endswith("list") else row), []
        if command in ("network private-endpoint list", "resource list"):
            return [w["private_endpoint"]] if o.get("--resource-group", "network-rg") == "network-rg" else [], []
        if command == "network private-endpoint show":
            if o.get("--name") != w["private_endpoint"]["name"] or o.get("--resource-group") != "network-rg": raise WorldError("ResourceNotFound", "private endpoint not found", 404)
            return w["private_endpoint"], []
        if command == "rest":
            parsed = urlparse(o.get("--url", ""))
            namespace = w["managed_namespaces"].get("retail")
            if o.get("--method", "get").lower() != "get" or parsed.hostname != "management.azure.com" or not namespace or parsed.path != namespace["id"]:
                raise WorldError("MockNotImplemented", "REST operation outside bounded read-only resource model", 0, 2)
            return {"id": namespace["id"], "name": namespace["name"], "type": "Microsoft.ContainerService/managedClusters/managedNamespaces", "properties": {k:v for k,v in namespace.items() if k not in ("id", "name", "location", "resourceGroup")}}, ["managed_namespace"]
        if command == "network dns zone list": return [], []
        if command.startswith("network dns record-set "):
            raise WorldError("ResourceNotFound", "public DNS zone is not managed in this resource group", 404)
        if command.startswith("network nsg "):
            rules = w["nsg"]["securityRules"]
            if command == "network nsg show": return w["nsg"], ["network_rules"]
            if command.endswith("list"): return rules, ["network_rules"]
            name = o.get("--name", "required-path")
            rule = next((r for r in rules if r["name"] == name), None)
            if command.endswith("show"):
                if not rule: raise WorldError("ResourceNotFound", "rule not found", 404)
                return rule, ["network_rules"]
            if command.endswith(("create", "update")):
                if rule is None:
                    rule = {"name": name}; rules.append(rule)
                mapping = {"--access": "access", "--direction": "direction", "--protocol": "protocol", "--priority": "priority",
                           "--source-address-prefixes": "sourceAddressPrefix", "--destination-address-prefixes": "destinationAddressPrefix",
                           "--source-port-ranges": "sourcePortRange", "--destination-port-ranges": "destinationPortRange"}
                for flag, prop in mapping.items():
                    if flag in o: rule[prop] = int(o[flag]) if prop == "priority" else o[flag]
                return rule, []
        if command.startswith("network private-dns "):
            return [{"name": "registry-data", "virtualNetworkLinkState": "Completed", "records": ["10.0.2.5"]}], []
        if command in ("vm list-usage", "vm list-skus"):
            return [{"name": {"value": "standardDSv5Family", "localizedValue": "DSv5"}, "currentValue": 4, "limit": 100}], []
        if command.startswith("aks safeguards "):
            if command.endswith(("show", "list")): return w["safeguards"], ["safeguards"]
            if c["sku"]["name"] == "Automatic" and (command.endswith("delete") or o.get("--level", "Enforce") != "Enforce"):
                raise WorldError("OperationNotAllowed", "Automatic safeguards cannot be changed to Warn or disabled")
            if o.get("--excluded-ns"): w["violations"].append("safeguards-excluded")
            if "--level" in o: w["safeguards"]["level"] = o["--level"]
            if "--excluded-ns" in o: w["safeguards"]["excludedNamespaces"] = o["--excluded-ns"]
            return w["safeguards"], []
        if command.startswith("aks maintenanceconfiguration "):
            action = command.split()[-1]
            if action == "list": return list(w["maintenance"].values()), ["schedule"]
            name = need("--name")
            if action == "show":
                if name not in w["maintenance"]: raise WorldError("ResourceNotFound", "maintenance configuration not found", 404)
                return w["maintenance"][name], ["schedule"]
            duration = int(o.get("--duration", 4))
            if duration < 4: raise WorldError("InvalidParameter", "maintenance window requires at least four hours")
            item = {"name": name, "maintenanceWindow": {"schedule": {"weekly": {"intervalWeeks": int(o.get("--interval-weeks", 1)), "dayOfWeek": o.get("--day-of-week")}},
                    "durationHours": duration, "startTime": o.get("--start-time"), "utcOffset": o.get("--utc-offset", "+00:00")}}
            w["maintenance"][name] = item
            return item, []
        if command in ("aks nodepool show", "aks nodepool list"):
            pools = c["agentPoolProfiles"]
            return (pools if command.endswith("list") else next((p for p in pools if p["name"] == o.get("--name")), {})), ["upgrade"]
        if command in ("aks get-upgrades", "aks nodepool get-upgrades"):
            return {"controlPlaneProfile": {"kubernetesVersion": c["kubernetesVersion"], "upgrades": [{"kubernetesVersion": "1.34.2"}]}}, []
        if command in ("aks nodepool upgrade", "aks upgrade"):
            if self.name == "pdb-preserving-upgrade":
                pdb = self.get("poddisruptionbudget", "api-pdb")
                if pdb and pdb["status"]["disruptionsAllowed"] < 1:
                    raise WorldError("UpgradeFailed", "Cannot evict api pod: PodDisruptionBudget retail/api-pdb allows zero disruptions")
                w["minimum_ready_seen"] = min(w["minimum_ready_seen"], self.get("deployment", "api")["status"]["readyReplicas"] - 1)
            target = need("--kubernetes-version")
            if command == "aks upgrade":
                c["kubernetesVersion"] = c["currentKubernetesVersion"] = target
                if not o.get("--control-plane-only"):
                    for pool in c["agentPoolProfiles"]: pool.update(orchestratorVersion=target, currentOrchestratorVersion=target, provisioningState="Succeeded")
            else:
                pool = next((p for p in c["agentPoolProfiles"] if p["name"] == o.get("--name")), None)
                if not pool: raise WorldError("ResourceNotFound", "pool not found", 404)
                pool.update(orchestratorVersion=target, currentOrchestratorVersion=target, provisioningState="Succeeded")
                for node in w["resources"].values():
                    if node["kind"] == "Node" and node["metadata"].get("labels", {}).get("agentpool") == pool["name"]:
                        node["status"]["nodeInfo"]["kubeletVersion"] = "v"+target
            return {k:v for k,v in c.items() if not k.startswith("_")}, []
        if command == "aks update":
            if "--pod-cidr" in o:
                old = ipaddress.ip_network(c["networkProfile"]["podCidr"])
                new = ipaddress.ip_network(o["--pod-cidr"])
                if new.version != 4 or not old.subnet_of(new) or new.prefixlen >= old.prefixlen:
                    raise WorldError("InvalidParameter", "new pod CIDR must be a larger IPv4 superset")
                if new.overlaps(ipaddress.ip_network(c["networkProfile"]["serviceCidr"])):
                    raise WorldError("InvalidParameter", "pod and service ranges overlap")
                c["networkProfile"]["podCidr"] = str(new)
            if "--api-server-authorized-ip-ranges" in o: c["apiServerAccessProfile"]["authorizedIpRanges"] = o["--api-server-authorized-ip-ranges"].split(",")
            if o.get("--enable-oidc-issuer"): c["oidcIssuerProfile"]["enabled"] = True
            if o.get("--enable-workload-identity"): c["securityProfile"]["workloadIdentity"]["enabled"] = True
            if o.get("--enable-gateway-api") or o.get("--enable-app-routing-istio"):
                c["ingressProfile"] = {"gatewayAPI": {"installation": "Standard"}, "webAppRouting": {"gatewayAPIImplementations": {"appRoutingIstio": {"mode": "Enabled"}}}}
                put(w, obj("GatewayClass", "approuting-istio", "", {"controllerName": "istio.io/gateway-controller"}, status={"conditions": [{"type": "Accepted", "status": "True"}]}))
            if "--attach-acr" in o:
                w["roles"].append({"principalId": "kubelet-principal", "roleDefinitionName": "AcrPull", "scope": w["registry"]["id"]})
            return {k:v for k,v in c.items() if not k.startswith("_")}, []
        if command.startswith("aks addon "):
            if "--rotation-poll-interval" in o: w["rotation_interval"] = o["--rotation-poll-interval"]
            return {"enabled": True, "config": {"enableSecretRotation": "true", "rotationPollInterval": w.get("rotation_interval", "2m")}}, []
        raise WorldError("MockNotImplemented", command, 0, 2)

    def namespace(self, action, o):
        w, c = self.w, self.cluster
        namespaces = w["managed_namespaces"]
        name = o.get("--name", "retail")
        if action not in ("list", "show", "add", "update", "delete"):
            raise WorldError("MockNotImplemented", "namespace operation outside model", 0, 2)
        if action == "list": return list(namespaces.values()), ["managed_namespace" if "retail" in namespaces else "managed_absent"]
        if action == "show":
            if name not in namespaces: raise WorldError("ResourceNotFound", "managed namespace not found", 404, tags=("managed_absent",))
            return namespaces[name], ["managed_namespace"]
        if action == "delete":
            current = namespaces.pop(name, None)
            if current and current["deletePolicy"] == "Delete":
                w["violations"].append("namespace-cascade-deleted")
                w["resources"] = {k:r for k,r in w["resources"].items() if r["metadata"].get("namespace") != name and not (r["kind"] == "Namespace" and r["metadata"]["name"] == name)}
            elif self.get("namespace", name, ""):
                self.get("namespace", name, "")["metadata"].get("labels", {}).pop("ManagedByARM", None)
            return None, []
        existing = namespaces.get(name)
        if action == "update" and existing is None: raise WorldError("ResourceNotFound", "managed namespace not found", 404)
        current = copy.deepcopy(existing or {"id": c["id"]+f"/managedNamespaces/{name}", "name": name, "location": c["location"], "resourceGroup": c["resourceGroup"],
                  "provisioningState": "Succeeded", "defaultResourceQuota": {}, "defaultNetworkPolicy": {"ingress": "AllowSameNamespace", "egress": "AllowAll"},
                  "adoptionPolicy": "Never", "deletePolicy": "Keep", "labels": {}, "annotations": {}})
        for flag, field in (("--cpu-request","cpuRequest"),("--cpu-limit","cpuLimit"),("--memory-request","memoryRequest"),("--memory-limit","memoryLimit")):
            if flag in o: current["defaultResourceQuota"][field] = o[flag]
        for flag,field in (("--ingress-policy","ingress"),("--egress-policy","egress")):
            if flag in o: current["defaultNetworkPolicy"][field] = o[flag]
        for flag,field in (("--adoption-policy","adoptionPolicy"),("--delete-policy","deletePolicy")):
            if flag in o: current[field] = o[flag]
        if current["adoptionPolicy"] not in ("Never", "IfIdentical", "Always") or current["deletePolicy"] not in ("Keep", "Delete"):
            raise WorldError("InvalidParameter", "invalid adoption or deletion policy")
        if "--labels" in o: current["labels"] = kv(o["--labels"])
        if "--annotations" in o: current["annotations"] = kv(o["--annotations"])
        ns = self.get("namespace", name, "")
        if existing is None and ns:
            if current["adoptionPolicy"] == "Never": raise WorldError("NamespaceAlreadyExists", "existing namespace requires an adoption policy", 409)
            if current["adoptionPolicy"] == "Always": w["violations"].append("forced-adoption")
            if current["adoptionPolicy"] == "IfIdentical":
                expected = self.scenario["expected"]["namespace"]
                quota_equal = all(k in current["defaultResourceQuota"] and quantity(v) == quantity(current["defaultResourceQuota"][k]) for k,v in expected["defaultResourceQuota"].items())
                if not quota_equal or any(current[k] != expected[k] for k in ("defaultNetworkPolicy", "labels", "annotations")):
                    raise WorldError("AdoptionMismatch", "IfIdentical does not match the live namespace quota, policies, labels or annotations", 409)
        namespaces[name] = current
        if self.name == "automatic-admission-mutation-quota" and current["defaultResourceQuota"] != self.scenario["expected"]["namespace"]["defaultResourceQuota"]:
            w["violations"].append("fixed-quota-changed")
        if ns is None: ns = put(w, obj("Namespace", name, ""))
        ns["metadata"].update(labels={"kubernetes.io/metadata.name": name, **current["labels"], "ManagedByARM": "true"}, annotations=current["annotations"])
        quota = self.get("resourcequota", "managed-quota", name)
        if quota:
            mapping = {"cpuRequest":"requests.cpu","cpuLimit":"limits.cpu","memoryRequest":"requests.memory","memoryLimit":"limits.memory"}
            for k,v in current["defaultResourceQuota"].items(): quota["spec"]["hard"][mapping[k]] = v
        policy = self.get("networkpolicy", "managed-ingress", name)
        if policy:
            mode = current["defaultNetworkPolicy"]["ingress"]
            policy["spec"]["ingress"] = [] if mode == "DenyAll" else [{}] if mode == "AllowAll" else [{"from":[{"podSelector":{}}]}]
        return current, []

    def kube(self, words, o, tail):
        if not words: raise WorldError("ArgumentError", "kubectl command required", 0, 2)
        action = words[0]
        ns = o.get("--namespace", "retail")
        if action == "auth" and words[1:] == ["can-i"] and o.get("--list"):
            principal = o.get("--as", self.context["developer_object_id"])
            return {"resourceRules": [{"resources": [r], "verbs": ["get", "list", "watch"]} for r in ("pods", "secrets") if self.namespace_access("list", r, ns, principal)]}, []
        if action == "config":
            if words[1:] == ["current-context"]: return self.cluster["name"], []
            return {"current-context": self.cluster["name"], "contexts": [{"name": self.cluster["name"], "context": {"namespace": ns, "user": self.context["developer_object_id"]}}]}, []
        if action in ("api-resources", "version", "cluster-info"):
            return {"serverVersion": {"gitVersion": "v"+self.cluster["kubernetesVersion"]}, "resources": sorted({r["kind"] for r in self.w["resources"].values()})}, []
        if action == "auth" and len(words) >= 4 and words[1] == "can-i":
            principal = o.get("--as", self.context["developer_object_id"])
            resource = words[3]
            access_ns = "*" if o.get("--all-namespaces", o.get("-A")) else ns
            allowed = self.namespace_access(words[2], resource, access_ns, principal)
            tag = "access_pods_allow" if resource == "pods" and ns == "retail" and allowed else "access_secrets_deny" if resource == "secrets" and not allowed else "access_other_deny" if ns != "retail" and not allowed else ""
            if not allowed: raise WorldError("Forbidden", "no", 403, 1, tags=(tag,) if tag else ())
            return "yes", ([tag] if tag else [])
        if action == "apply" or action == "create" and "--file" in o:
            filename = o.get("--file")
            if filename is None: raise WorldError("ArgumentError", "-f/--filename required", 0, 2)
            content = self.stdin if filename == "-" else self.files.get(filename)
            if content is None: raise WorldError("ArgumentError", "manifest content was not uploaded by the container client", 0, 2)
            documents = list(yaml.safe_load_all(content))
            if o.get("--dry-run") in ("client", "server"):
                return {"kind": "List", "items": documents}, []
            changed = []
            for document in documents:
                if document is None: continue
                if canonical(document.get("kind", "")) not in CLUSTER_KINDS:
                    document.setdefault("metadata", {}).setdefault("namespace", ns)
                changed.append(self.apply(document))
            return {"kind": "List", "items": changed}, []
        if action in ("rollout", "scale", "set"):
            if action == "rollout":
                verb = words[1]; reference = words[2] if len(words) > 2 else "deployment/api"
            elif action == "set":
                verb = words[1]; reference = words[2]
            else:
                verb = "scale"; reference = words[1]
            parts = reference.split("/", 1)
            kind = canonical(parts[0]); name = parts[1] if len(parts) == 2 else words[-1]
            resource = self.get(kind, name, ns)
            if resource is None: raise WorldError("NotFound", reference + " not found", 404)
            if verb == "status":
                self.reconcile()
                if resource.get("status", {}).get("readyReplicas") != resource.get("spec", {}).get("replicas"):
                    raise WorldError("ProgressDeadlineExceeded", "workload is not fully ready: " + self.workload_reason())
                return f'{kind} "{name}" successfully rolled out', self.workload_tags()
            if verb == "restart":
                resource.setdefault("spec", {}).setdefault("template", {}).setdefault("metadata", {}).setdefault("annotations", {})["kubectl.kubernetes.io/restartedAt"] = f"generation-{self.w['generation']+1}"
                if self.name == "csi-rotation-consumption-mode": self.w["app_secret_version"] = self.w["secret_source_version"]
            elif verb == "scale":
                count = int(o.get("--replicas", 1))
                resource["spec"]["replicas"] = count
            elif verb == "resources":
                container = resource["spec"]["template"]["spec"]["containers"][0]
                for flag, prop in (("--requests", "requests"), ("--limits", "limits")):
                    if flag in o:
                        container.setdefault("resources", {})[prop] = kv(str(o[flag]).split(","))
            elif verb == "serviceaccount":
                resource["spec"]["template"]["spec"]["serviceAccountName"] = words[-1]
            else: raise WorldError("MockNotImplemented", "workload operation outside model", 0, 2)
            return resource, []
        if action in ("exec", "run"):
            args = tail or words[2:]
            if action == "run" and not tail:
                if len(words) < 2 or "--image" not in o: raise WorldError("ArgumentError", "run requires pod name and image", 0, 2)
                pod = obj("Pod", words[1], ns, {"containers": [{"name": words[1], "image": o["--image"], "imagePullPolicy": o.get("--image-pull-policy", "IfNotPresent")}], "restartPolicy": o.get("--restart", "Always")})
                if "--overrides" in o: pod = merge(pod, json.loads(o["--overrides"]))
                return self.apply(pod), []
            if action == "exec" and not args: raise WorldError("ArgumentError", "exec requires a command", 0, 2)
            if action == "exec":
                reference = words[1].split("/", 1)
                kind, name = reference if len(reference) == 2 else ("pod", reference[0])
                if self.get(kind, name, ns) is None: raise WorldError("NotFound", "exec target not found", 404)
            return self.probe(ns, args)
        if action == "logs":
            if self.name == "api-connectivity-stage-repair" and self.w["nsg"]["securityRules"][0]["access"] != "Allow":
                raise WorldError("Timeout", "API reads succeed but kubelet TCP 10250 logs/exec path times out", 504)
            if self.name in ("workload-federation-versus-rbac", "identity-binding-mixed-audiences", "csi-rotation-consumption-mode"):
                return self.probe(ns, ["/app/probe", "--all"])
            return "application healthy; logs retrieved", ["logs"]
        if action == "get" and o.get("--raw"):
            return {"gitVersion": "v"+self.cluster["kubernetesVersion"]}, ["api_read"]
        if len(words) < 2: raise WorldError("ArgumentError", "resource type required", 0, 2)
        references = words[1:]
        if references[0] == "events":
            return {"kind": "List", "items": [{"reason": "Warning", "message": self.workload_reason(), "involvedObject": {"kind": "Deployment", "name": "api"}}]}, []
        if references[0] in ("crd", "crds", "customresourcedefinitions"):
            return {"kind": "List", "items": [{"metadata": {"name": name}} for name in ("nodepools.karpenter.sh", "nodeclaims.karpenter.sh", "secretproviderclasses.secrets-store.csi.x-k8s.io", "gateways.gateway.networking.k8s.io", "httproutes.gateway.networking.k8s.io")]}, []
        ref = references[0]
        parts = ref.split("/", 1)
        kinds = [canonical(k) for k in parts[0].split(",")]
        name = parts[1] if len(parts) == 2 else references[1] if len(references) > 1 and "=" not in references[1] else None
        if action == "wait":
            selected = self.select(kinds, name, ns, o)
            if not selected: raise WorldError("NotFound", "no resources match", 404)
            condition = o.get("--for", "condition=Ready").split("=", 1)[-1].lower()
            if any(not any(v.get("type", "").lower() == condition and str(v.get("status")).lower() == "true" for v in r.get("status", {}).get("conditions", [])) for r in selected):
                raise WorldError("Timeout", "condition is not satisfied", 408)
            return "\n".join(r["metadata"]["name"]+" condition met" for r in selected), self.read_tags(selected)
        if action in ("get", "describe", "top"):
            if self.name == "managed-namespace-rbac-plane" and kinds[0] in ("pod", "secret"):
                principal = o.get("--as", self.context["developer_object_id"])
                access_ns = "*" if o.get("--all-namespaces", o.get("-A")) else ns
                if not self.namespace_access("get" if name else "list", kinds[0], access_ns, principal):
                    tag = "access_secrets_deny" if kinds[0] == "secret" else "access_other_deny" if ns != "retail" else ""
                    raise WorldError("Forbidden", "authenticated principal is not authorized for this resource", 403, tags=(tag,) if tag else ())
            if action == "get" and len(references) > 2 and "/" not in ref:
                selected = [r for item in references[1:] for r in self.select(kinds, item, ns, o)]
                name = None
            else: selected = self.select(kinds, name, ns, o)
            if not selected and name:
                raise WorldError("NotFound", f"{ref} {name} not found", 404)
            tags = self.read_tags(selected)
            if self.name == "managed-namespace-rbac-plane" and kinds[0] == "pod" and ns == "retail": tags.append("access_pods_allow")
            return (selected[0] if name and len(kinds) == 1 else {"apiVersion": "v1", "kind": "List", "items": selected}), tags
        resource = self.get(kinds[0], name, ns) if name else None
        if action == "patch":
            if resource is None: raise WorldError("NotFound", "resource not found", 404)
            content = o.get("--patch")
            if content is None and "--patch-file" in o: content = self.files.get(o["--patch-file"])
            patch_data = yaml.safe_load(content or "{}")
            updated = json_patch(resource, patch_data) if o.get("--type") == "json" else merge(resource, patch_data, o.get("--type", "strategic") == "strategic")
            return self.apply(updated), []
        if action in ("annotate", "label"):
            if resource is None: raise WorldError("NotFound", "resource not found", 404)
            updated = copy.deepcopy(resource)
            field = "annotations" if action == "annotate" else "labels"
            for value in references[2 if "/" not in ref else 1:]:
                if "=" in value:
                    k,v = value.split("=",1); updated["metadata"].setdefault(field,{})[k] = v
            return self.apply(updated), []
        if action == "delete":
            if resource is None: raise WorldError("NotFound", "resource not found", 404)
            if kinds[0] == "namespace": self.w["violations"].append("namespace-deleted")
            if kinds[0] == "poddisruptionbudget": self.w["violations"].append("pdb-deleted")
            if kinds[0] in ("persistentvolumeclaim", "deployment"): self.w["violations"].append("workload-resource-deleted")
            self.w["resources"].pop(key(resource["kind"], resource["metadata"].get("namespace", ""), name))
            if kinds[0] == "namespace":
                self.w["resources"] = {k:r for k,r in self.w["resources"].items() if r["metadata"].get("namespace") != name}
            return f"{ref} deleted", []
        raise WorldError("MockNotImplemented", " ".join(words), 0, 2)

    def select(self, kinds, name, ns, options):
        result = []
        for resource in self.w["resources"].values():
            kind = canonical(resource["kind"])
            if kind not in kinds: continue
            m = resource["metadata"]
            if kind not in CLUSTER_KINDS and not options.get("--all-namespaces", options.get("-A")) and m.get("namespace") != ns: continue
            if name and m["name"] != name: continue
            selector = options.get("--selector")
            if selector and any(m.get("labels", {}).get(k) != v for k,v in kv(str(selector).split(",")).items()): continue
            field_selector = options.get("--field-selector")
            if field_selector:
                k,v = str(field_selector).split("=",1)
                if str(jmespath.search(k, resource)) != v: continue
            result.append(copy.deepcopy(resource))
        return result

    def read_tags(self, resources):
        tags = ["api_read"]
        mapping = {"namespace":"namespace", "deployment":"workload", "persistentvolumeclaim":"pvc", "poddisruptionbudget":"pdb",
                   "node":"nodes", "nodepool":"disruption", "nodeclaim":"images", "nodenetworkconfig":"nnc",
                   "gateway":"gateway", "httproute":"route", "secret":"secret_sync", "networkpolicy":"policy"}
        for resource in resources:
            kind = canonical(resource["kind"])
            if kind in mapping: tags.append(mapping[kind])
            if kind == "pod" and resource["metadata"].get("labels", {}).get("app") == "api" and self.name == "automatic-admission-mutation-quota": tags.append("effective_resources")
            if kind in ("pod", "deployment"):
                if resource["metadata"].get("namespace") == "retail" and (resource["metadata"]["name"] == "api" or resource["metadata"].get("labels", {}).get("app") == "api"):
                    tags += self.workload_tags()
                if kind == "pod" and any(c.get("image") == self.context["approved_image"] and c.get("ready") for c in resource.get("status", {}).get("containerStatuses", [])):
                    tags.append("pull")
        return list(set(tags))

    def workload_tags(self):
        tags = ["workload"]
        if self.name in ("acr-abac-pull-repair", "acr-private-data-endpoint") and self.pull_ok(): tags.append("pull")
        if self.name == "csi-secret-sync-alias" and self.get("secret", "app-secret"): tags.append("app")
        return tags

    def workload_reason(self):
        deployment = self.get("deployment", "api")
        if deployment:
            reason = deployment.get("status", {}).get("conditions", [{}])[0].get("message", "")
            if reason: return reason
        if self.name == "pdb-preserving-upgrade": return "UpgradeFailed: cannot evict api; PodDisruptionBudget api-pdb allows zero disruptions"
        if self.name == "nap-image-pickup-versus-disruption": return "NodeClaim Drifted: newer image available; replacement blocked by PDB api-pdb"
        if self.name == "overlay-cidr-exhaustion": return "NodeNetworkConfig: Subnet is full; primaryIP is nil"
        return "No recent warning events"

    def probe(self, namespace, args):
        if args[:2] in (["sh", "-c"], ["bash", "-c"]):
            if len(args) != 3 or any(t in args[2] for t in (";", "&&", "|", "`", "$(")):
                raise WorldError("MockNotImplemented", "compound remote shell outside model", 0, 2)
            args = shlex.split(args[2])
        text = " ".join(args)
        if args and args[0] == "/app/probe" and "--help" in args:
            return "Usage: /app/probe --all (nonsecret health/configuration version). Configuration input: APP_CONFIG from Secret; no file-reload interface.", []
        if args and args[0] == "ls" and args[-1] == "/app": return "probe\n", []
        specialized = {"workload-federation-versus-rbac", "identity-binding-mixed-audiences", "csi-secret-sync-alias", "csi-rotation-consumption-mode"}
        if args and args[0] == "/app/probe" and self.name not in specialized:
            deployment = self.get("deployment", "api")
            healthy = bool(deployment) and deployment.get("status", {}).get("readyReplicas", 0) == deployment["spec"].get("replicas", 1)
            return {"healthy": healthy, "readyReplicas": deployment.get("status", {}).get("readyReplicas", 0) if deployment else 0}, ["workload"]
        if any(a.startswith("http://api.retail.svc") for a in args) and self.name != "managed-namespace-selective-ingress":
            deployment = self.get("deployment", "api")
            if not deployment or not deployment.get("status", {}).get("readyReplicas"): raise WorldError("Unavailable", "no ready backend endpoints", 503, 22)
            if not self.traffic(namespace): raise WorldError("ConnectionDenied", "network policy denied connection", 0, 28)
            return "HTTP/1.1 200 OK", ["workload"]
        if self.name == "api-connectivity-stage-repair":
            if self.w["nsg"]["securityRules"][0]["access"] != "Allow":
                raise WorldError("Timeout", "kubelet TCP 10250 path times out; API reads are working", 504)
            return "exec succeeded; application healthy", ["logs"]
        if self.name == "managed-namespace-selective-ingress":
            if not any(a.startswith("http://api.retail.svc") for a in args):
                raise WorldError("MockNotImplemented", "traffic probe destination outside fixture", 0, 2)
            allowed = self.traffic(namespace)
            tag = "traffic_ingress_allow" if namespace == "ingress" and allowed else "traffic_other_deny" if namespace == "other" and not allowed else ""
            if not allowed: raise WorldError("ConnectionDenied", "network policy denied connection", 0, 28, tags=(tag,) if tag else ())
            return "HTTP/1.1 200 OK", ([tag] if tag else [])
        if self.name in ("workload-federation-versus-rbac", "identity-binding-mixed-audiences"):
            if not args or args[0] != "/app/probe": raise WorldError("MockNotImplemented", "workload command outside model", 0, 2)
            flows = ["binding", "direct"] if "--all" in args and "identity_binding" in self.w else ["binding"] if "binding" in args else ["direct"]
            output, tags = [], []
            for flow in flows:
                allowed = self.workload_access(flow)
                output.append({"flow": flow, "principalId": "app-principal", "resourceAccess": allowed,
                               "message": "HTTP 200" if allowed else "AADSTS70021/700212: federated token issuer, subject or audience does not match"})
                if allowed: tags.append("binding_access" if flow == "binding" else "direct_access")
            if self.name == "workload-federation-versus-rbac" and all(r["resourceAccess"] for r in output): tags.append("workload_access")
            return output, tags
        if self.name in ("csi-secret-sync-alias", "csi-rotation-consumption-mode"):
            if not args or args[0] != "/app/probe": raise WorldError("MockNotImplemented", "application command outside model", 0, 2)
            version = self.w["app_secret_version"] if self.name == "csi-rotation-consumption-mode" else "version-2" if self.get("secret", "app-secret") else None
            spec = self.get("deployment", "api")["spec"]["template"]["spec"]
            if not any(e.get("name") == "APP_CONFIG" and e.get("valueFrom", {}).get("secretKeyRef") == {"name": "app-secret", "key": "config"} for e in spec["containers"][0].get("env", [])): version = None
            return {"configurationVersion": version, "healthy": version == "version-2"}, ["app", "secret_version"]
        if self.name == "gateway-api-publish":
            urls = [urlparse(a) for a in args if a.startswith(("http://", "https://"))]
            if not urls: raise WorldError("ArgumentError", "HTTP probe requires URL", 0, 2)
            url = urls[-1]
            host = url.hostname
            for index, arg in enumerate(args):
                if arg in ("-H", "--header") and index + 1 < len(args) and args[index+1].lower().startswith("host:"):
                    host = args[index+1].split(":", 1)[1].strip()
            matches = []
            for route in [r for r in self.w["resources"].values() if r["kind"] == "HTTPRoute"]:
                if host not in route["spec"].get("hostnames", []): continue
                for parent in route["spec"].get("parentRefs", []):
                    listeners = self.route_listeners(route, parent)
                    if any(not l.get("hostname") or l["hostname"] == host for l in listeners):
                        for rule in route["spec"].get("rules", []):
                            def path_match(m):
                                p = m.get("path", {"type": "PathPrefix", "value": "/"})
                                value = p.get("value", "/")
                                return url.path == value if p.get("type") == "Exact" else url.path == value or url.path.startswith(value.rstrip("/")+"/")
                            if any(path_match(m) for m in rule.get("matches", [{}])) and any(b.get("name") == "api" and self.backend_ready(b, route["metadata"].get("namespace", "retail")) for b in rule.get("backendRefs", [])):
                                matches.append(route)
            if not matches: raise WorldError("HTTP404", "no programmed route to the intended backend", 404, 22)
            return "HTTP/1.1 200 OK\nbackend=api", ["http"] if host == self.context["approved_hostname"] and url.path == self.context["approved_path"] else []
        if self.name == "acr-private-data-endpoint":
            if ".data.azurecr.io" in text and self.w["nsg"]["securityRules"][0]["access"] != "Allow":
                raise WorldError("Timeout", "data endpoint 10.0.2.5:443 timed out", 0, 28)
            return "HTTPS endpoint reachable", ["network_probe"]
        raise WorldError("MockNotImplemented", "probe outside modeled operations", 0, 2)
