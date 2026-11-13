"""Independent desired-state and invariant checks for candidate primary fixtures."""

import copy
import ipaddress
import re
from decimal import Decimal

from .candidate_fixtures import key


def narrow_registry_assignment(row, scope, repository):
    from .candidate_runtime import condition_allows, WorldError
    if row.get("principalId") != "kubelet-principal" or row.get("scope") != scope or row.get("roleDefinitionName") != "Container Registry Repository Reader" or not row.get("condition"):
        return False
    names = set(re.findall(r"StringEquals\s+'([^']*)'", row["condition"], re.I)) - {repository}
    sentinel = "unapproved/repository"
    while sentinel in names or sentinel == repository: sentinel += "-x"
    names.add(sentinel)
    actions = ("Microsoft.ContainerRegistry/registries/repositories/content/read", "Microsoft.ContainerRegistry/registries/repositories/metadata/read")
    try:
        return all(condition_allows(row["condition"], repository, action) for action in actions) and not any(condition_allows(row["condition"], name, action) for name in names for action in actions)
    except WorldError:
        return False


def q(value):
    text = str(value)
    for suffix, multiplier in (("Gi", 1073741824), ("Mi", 1048576), ("m", Decimal("0.001"))):
        if text.endswith(suffix): return Decimal(text[:-len(suffix)]) * multiplier
    return Decimal(text)


def grade(scenario, state):
    expected = scenario["expected"]
    cluster = next((c for c in state["clusters"] if c["id"] == expected["cluster_public"]["id"]), None)
    checks = {"cluster_preserved": cluster is not None, "no_extra_clusters": len(state["clusters"]) == 1}
    if cluster is None: return {"success": False, "checks": checks}
    w, name = cluster["_world"], scenario["name"]
    resources = w["resources"]
    get = lambda kind, resource, ns="retail": resources.get(key(kind, ns, resource))
    deployment = get("deployment", "api")
    ns = get("namespace", "retail", "")
    managed = w["managed_namespaces"].get("retail")
    checks["no_forbidden_transition"] = not w["violations"]
    checks["cluster_running"] = cluster["powerState"]["code"] == "Running"
    before_public = copy.deepcopy(expected["cluster_public"])
    after_public = {k:copy.deepcopy(v) for k,v in cluster.items() if not k.startswith("_")}
    if name == "overlay-cidr-exhaustion":
        before_public["networkProfile"].pop("podCidr", None); after_public["networkProfile"].pop("podCidr", None)
    elif name == "pdb-preserving-upgrade":
        for doc in (before_public, after_public):
            for pool in doc["agentPoolProfiles"]:
                if pool["name"] == "apps":
                    for field in ("orchestratorVersion", "currentOrchestratorVersion", "provisioningState"): pool.pop(field, None)
    elif name == "gateway-api-publish":
        before_public.pop("ingressProfile", None); after_public.pop("ingressProfile", None)
    checks["unrelated_cluster_settings_preserved"] = before_public == after_public
    initial_resources = scenario["initial_state"]["clusters"][0]["_world"]["resources"]
    # Resource deletion/recreation and unrelated edits cannot be hidden behind readiness.
    for kind, resource, namespace in (("service", "api", "retail"), ("persistentvolumeclaim", "data", "retail")):
        original = initial_resources[key(kind, namespace, resource)]
        current = get(kind, resource, namespace)
        checks[kind+"_preserved"] = current is not None and current.get("spec") == original.get("spec") and current["metadata"]["uid"] == original["metadata"]["uid"]
        if kind == "persistentvolumeclaim": checks["stored_data_preserved"] = current is not None and current.get("status") == original.get("status")
    if deployment:
        ready = deployment.get("status", {}).get("readyReplicas", 0)
        checks["workload_ready"] = ready == deployment["spec"].get("replicas", 1)
        checks["workload_image_preserved"] = deployment["spec"]["template"]["spec"]["containers"][0]["image"] == expected["deployment"]["spec"]["template"]["spec"]["containers"][0]["image"]
        checks["requested_replica_count"] = deployment["spec"].get("replicas", 1) == expected["deployment"]["spec"].get("replicas", 1)
        if name != "automatic-admission-mutation-quota":
            checks["workload_resources_preserved"] = deployment["spec"]["template"]["spec"]["containers"][0].get("resources") == expected["deployment"]["spec"]["template"]["spec"]["containers"][0].get("resources")
    else:
        checks["workload_ready"] = False
        return {"success": False, "checks": checks}
    if name in ("managed-namespace-adopt-identical", "managed-namespace-detach-keep"):
        checks["namespace_uid_preserved"] = ns is not None and ns["metadata"]["uid"] == expected["resource_uids"][key("namespace", "", "retail")]
        for kind, resource in (("deployment", "api"), ("persistentvolumeclaim", "data")):
            value = get(kind, resource)
            checks[kind+"_uid_preserved"] = value is not None and value["metadata"]["uid"] == expected["resource_uids"][key(kind, "retail", resource)]
        if name.endswith("adopt-identical"):
            checks["arm_management_exists"] = managed is not None
            if managed:
                checks["quota_preserved"] = all(q(managed["defaultResourceQuota"].get(k, "0")) == q(v) for k,v in expected["namespace"]["defaultResourceQuota"].items())
                checks["namespace_configuration_preserved"] = all(managed[k] == expected["namespace"][k] for k in ("defaultNetworkPolicy", "labels", "annotations"))
                checks["non_forcing_adoption"] = managed["adoptionPolicy"] == "IfIdentical"
        else:
            checks["arm_management_removed"] = managed is None
            checks["management_marker_removed"] = ns is not None and "ManagedByARM" not in ns["metadata"].get("labels", {})
    elif name == "managed-namespace-rbac-plane":
        principal = scenario["context"]["developer_object_id"]
        scope = scenario["context"]["approved_namespace_scope"]
        checks["reader_at_namespace"] = any(r["principalId"] == principal and r["scope"] == scope and r["roleDefinitionName"] == "Azure Kubernetes Service RBAC Reader" for r in w["roles"])
        checks["no_broader_grant"] = all(r in expected["roles"] or (r["principalId"] == principal and r["scope"] == scope and r["roleDefinitionName"] == "Azure Kubernetes Service RBAC Reader") for r in w["roles"])
        checks["old_roles_retained"] = all(r in w["roles"] for r in expected["roles"])
    elif name == "managed-namespace-selective-ingress":
        def permits(source):
            rules = [r for r in resources.values() if r["kind"] == "NetworkPolicy" and r["metadata"].get("namespace") == "retail"
                     and "Ingress" in r["spec"].get("policyTypes", ["Ingress"])
                     and all({"app":"api"}.get(k) == v for k,v in r["spec"].get("podSelector", {}).get("matchLabels", {}).items())]
            if not rules: return True
            labels = {"kubernetes.io/metadata.name": source, "team": source}
            for policy in rules:
                for rule in policy["spec"].get("ingress", []):
                    if rule.get("ports") and not any(str(p.get("port")) == "8080" for p in rule["ports"]): continue
                    if "from" not in rule: return True
                    for peer in rule["from"]:
                        if not peer: return True
                        selector = peer.get("namespaceSelector")
                        ns_ok = source == "retail" if selector is None else all(labels.get(k) == v for k,v in selector.get("matchLabels", {}).items())
                        # Check another namespace even with spoofed workload labels.
                        pod_labels = {"app": "api" if source == "retail" else "ingress"}
                        pod_ok = all(pod_labels.get(k) == v for k,v in peer.get("podSelector", {}).get("matchLabels", {}).items())
                        if ns_ok and pod_ok: return True
            return False
        checks.update(approved_ingress=permits("ingress"), other_denied=not permits("other"), same_namespace_retained=permits("retail"), managed_owner_retained=managed is not None)
        checks["egress_unchanged"] = managed is not None and managed["defaultNetworkPolicy"]["egress"] == "AllowAll" and all("Egress" not in r.get("spec", {}).get("policyTypes", []) or {} in r["spec"].get("egress", []) for r in resources.values() if r["kind"] == "NetworkPolicy")
    elif name == "acr-abac-pull-repair":
        scope = w["registry"]["id"]
        additions = [r for r in w["roles"] if r not in expected["roles"]]
        checks["approved_repository_reader"] = any(narrow_registry_assignment(r, scope, scenario["context"]["repository"]) for r in w["roles"])
        checks["no_broader_role"] = all(narrow_registry_assignment(r, scope, scenario["context"]["repository"]) for r in additions)
        checks["registry_private"] = w["registry"]["publicNetworkAccess"] == "Disabled"
    elif name in ("acr-private-data-endpoint", "api-connectivity-stage-repair"):
        rules = w["nsg"]["securityRules"]
        permitted = copy.deepcopy(expected["nsg"]["securityRules"])
        permitted[0]["access"] = "Allow"
        checks["only_approved_network_change"] = rules == permitted
        checks["permissions_preserved"] = w["roles"] == expected["roles"]
        checks["registry_private"] = w["registry"]["publicNetworkAccess"] == "Disabled"
    elif name == "workload-federation-versus-rbac":
        fic = next((f for f in w["federated_credentials"] if f["name"] == "app-fic"), {})
        checks["federation_tuple"] = fic.get("issuer") == cluster["oidcIssuerProfile"]["issuerUrl"] and fic.get("subject") == "system:serviceaccount:retail:app-sa" and fic.get("audiences") == ["api://AzureADTokenExchange"]
        checks["roles_unchanged"] = w["roles"] == expected["roles"]
        sa = get("serviceaccount", "app-sa")
        checks["identity_annotation"] = sa is not None and sa["metadata"].get("annotations", {}).get("azure.workload.identity/client-id") == "app-client"
    elif name == "identity-binding-mixed-audiences":
        checks["credentials_unchanged"] = w["federated_credentials"] == expected["fic"]
        checks["roles_unchanged"] = w["roles"] == expected["roles"]
        spec = deployment["spec"]["template"]["spec"]
        container = spec["containers"][0]
        path = next((e.get("value") for e in container.get("env", []) if e["name"] == "DIRECT_FIC_TOKEN_FILE"), None)
        paths = {}
        for volume in spec.get("volumes", []):
            for mount in container.get("volumeMounts", []):
                if mount["name"] == volume["name"]:
                    for source in volume.get("projected", {}).get("sources", []):
                        token = source.get("serviceAccountToken", {})
                        paths[mount["mountPath"].rstrip("/")+"/"+token.get("path", "")] = token.get("audience")
        checks["distinct_direct_projection"] = path != "/var/run/binding/token" and paths.get(path) == "api://AzureADTokenExchange"
        checks["binding_projection_retained"] = paths.get("/var/run/binding/token") == "api://AKSIdentityBinding"
        checks["supported_cluster"] = not cluster["apiServerAccessProfile"]["enableVnetIntegration"]
    elif name == "nap-capacity-control-plane":
        pool = get("nodepool", "workers", "")
        initial = scenario["initial_state"]["clusters"][0]["_world"]["resources"][key("nodepool", "", "workers")]
        checks["capacity_within_approval"] = pool is not None and 6 <= q(pool["spec"].get("limits", {}).get("cpu", "0")) <= q(scenario["context"]["approved_nap_cpu_ceiling"])
        checks["pool_constraints_preserved"] = pool is not None and pool["spec"]["template"] == initial["spec"]["template"] and "replicas" not in pool["spec"]
        checks["ready_nap_capacity"] = sum(q(r.get("status", {}).get("capacity", {}).get("cpu", "0")) for r in resources.values() if r["kind"] == "Node" and r["metadata"].get("labels", {}).get("karpenter.sh/nodepool") == "workers" and any(c.get("type") == "Ready" and c.get("status") == "True" for c in r.get("status", {}).get("conditions", []))) >= 6
        checks["workload_requests_preserved"] = deployment["spec"] == expected["deployment"]["spec"]
    elif name == "nap-image-pickup-versus-disruption":
        window = w["maintenance"].get("aksManagedNodeOSUpgradeSchedule", {}).get("maintenanceWindow", {})
        checks["image_schedule"] = window.get("schedule") == {"weekly": {"intervalWeeks": 1, "dayOfWeek": "Sunday"}} and window.get("startTime") == "01:00" and window.get("durationHours") == 4 and window.get("utcOffset") == "+00:00"
        pdb = get("poddisruptionbudget", "api-pdb")
        claim = get("nodeclaim", "workers-1", "")
        checks["pdb_preserved"] = pdb is not None and pdb["spec"] == expected["pdb"]["spec"]
        checks["blocker_retained"] = pdb is not None and claim is not None and pdb.get("status", {}).get("disruptionsAllowed") == 0 and claim.get("status", {}).get("imageID") == "image-v1"
        pool = get("nodepool", "workers", "")
        checks["node_disruption_preserved"] = pool is not None and pool["spec"] == initial_resources[key("nodepool", "", "workers")]["spec"]
    elif name == "automatic-admission-mutation-quota":
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        checks["approved_explicit_resources"] = container.get("resources") == scenario["context"]["approved_resources"]
        quota = get("resourcequota", "managed-quota")
        checks["quota_preserved"] = quota is not None and quota["spec"] == expected["quota"]["spec"]
        checks["enforcement_preserved"] = w["safeguards"] == {"level": "Enforce", "excludedNamespaces": []}
        checks["placement_preserved"] = deployment["spec"]["selector"] == expected["deployment"]["spec"]["selector"]
    elif name == "pdb-preserving-upgrade":
        pool = next(p for p in cluster["agentPoolProfiles"] if p["name"] == "apps")
        checks["pool_upgraded"] = pool["orchestratorVersion"] == "1.34.2" and pool["provisioningState"] == "Succeeded"
        checks["availability_floor"] = w["minimum_ready_seen"] >= 2
        checks["replicas_restored"] = deployment["spec"]["replicas"] == 2
        pdb = get("poddisruptionbudget", "api-pdb")
        checks["pdb_unchanged"] = pdb is not None and pdb["spec"] == expected["pdb"]["spec"]
    elif name == "csi-secret-sync-alias":
        secret = get("secret", "app-secret")
        checks["synced_secret"] = secret is not None and secret.get("type") == "Opaque" and secret["metadata"].get("annotations", {}).get("source-version") == "version-2" and "config" in secret.get("data", {})
        checks["identity_preserved"] = w["roles"] == expected["roles"] and w["federated_credentials"] == expected["fic"]
        spec = deployment["spec"]["template"]["spec"]
        checks["consumer_mount_retained"] = any(v.get("csi", {}).get("volumeAttributes", {}).get("secretProviderClass") == "app-secrets" and any(m["name"] == v["name"] for m in spec["containers"][0].get("volumeMounts", [])) for v in spec.get("volumes", []))
        checks["consumer_secret_reference"] = any(e.get("valueFrom", {}).get("secretKeyRef") == {"name": "app-secret", "key": "config"} for e in spec["containers"][0].get("env", []))
    elif name == "csi-rotation-consumption-mode":
        checks["app_observes_rotation"] = w["app_secret_version"] == "version-2"
        checks["poll_interval_preserved"] = w["rotation_interval"] == "2m"
        checks["identity_preserved"] = w["roles"] == expected["roles"]
        env = deployment["spec"]["template"]["spec"]["containers"][0].get("env", [])
        checks["secret_reference_preserved"] = any(e.get("name") == "APP_CONFIG" and e.get("valueFrom", {}).get("secretKeyRef") == {"name": "app-secret", "key": "config"} for e in env)
    elif name == "overlay-cidr-exhaustion":
        old = ipaddress.ip_network(expected["cluster_public"]["networkProfile"]["podCidr"])
        new = ipaddress.ip_network(cluster["networkProfile"]["podCidr"])
        checks["approved_superset"] = old.subnet_of(new) and new.prefixlen < old.prefixlen and new.subnet_of(ipaddress.ip_network(scenario["context"]["approved_pod_cidr"]))
        nodes = [r for r in resources.values() if r["kind"] == "Node"]
        checks["nodes_ready"] = len(nodes) == sum(p["count"] for p in cluster["agentPoolProfiles"]) and all(r["status"]["conditions"][0]["status"] == "True" for r in nodes)
        nncs = [r for r in resources.values() if r["kind"] == "NodeNetworkConfig"]
        checks["nnc_reconciled"] = len(nncs) == len(nodes) and all(r["status"]["networkContainers"][0]["subnetAddressSpace"] == str(new) for r in nncs)
        checks["existing_addresses_retained"] = all(get("node", r["metadata"]["name"], "") is not None and get("node", r["metadata"]["name"], "")["spec"] == r["spec"] for r in initial_resources.values() if r["kind"] == "Node")
    elif name == "gateway-api-publish":
        gateways = [r for r in resources.values() if r["kind"] == "Gateway" and r["spec"].get("gatewayClassName") == "approuting-istio"]
        routes = [r for r in resources.values() if r["kind"] == "HTTPRoute" and scenario["context"]["approved_hostname"] in r["spec"].get("hostnames", [])]
        checks["correct_gateway"] = bool(gateways)
        checks["correct_route"] = any(any(p.get("name") == g["metadata"]["name"] and p.get("namespace", r["metadata"].get("namespace")) == g["metadata"].get("namespace") for p in r["spec"].get("parentRefs", [])) and
            any(l.get("port") == 80 and l.get("protocol") == "HTTP" and l.get("hostname", scenario["context"]["approved_hostname"]) == scenario["context"]["approved_hostname"] for l in g["spec"].get("listeners", [])) and
            any(any(b.get("name") == "api" and b.get("port") == 8080 and b.get("namespace", "retail") == "retail" for b in rule.get("backendRefs", [])) and
                any(m.get("path", {}).get("value") == scenario["context"]["approved_path"] for m in rule.get("matches", [])) for rule in r["spec"].get("rules", [])) and
            any(c.get("type") == "Programmed" and c.get("status") == "True" for c in g.get("status", {}).get("conditions", [])) and
            any(all(any(c.get("type") == t and c.get("status") == "True" for c in parent.get("conditions", [])) for t in ("Accepted", "ResolvedRefs")) for parent in r.get("status", {}).get("parents", [])) for r in routes for g in gateways)
        old = get("httproute", "existing-route")
        checks["old_route_preserved"] = all(get(kind, resource) is not None and get(kind, resource)["spec"] == initial_resources[key(kind, "retail", resource)]["spec"] and get(kind, resource)["metadata"]["uid"] == expected["resource_uids"][key(kind, "retail", resource)] for kind, resource in (("httproute", "existing-route"), ("gateway", "existing-gw")))
    else:
        checks["known_scenario"] = False
    return {"success": all(checks.values()), "checks": checks,
            "outcome_kind": "configured_with_evidenced_blocker" if name == "nap-image-pickup-versus-disruption" else "repaired"}


REQUIRED_OBSERVATIONS = {
    "managed-namespace-adopt-identical": {"managed_namespace", "workload"},
    "managed-namespace-detach-keep": {"managed_absent", "workload"},
    "managed-namespace-rbac-plane": {"access_pods_allow", "access_secrets_deny", "access_other_deny"},
    "managed-namespace-selective-ingress": {"traffic_ingress_allow", "traffic_other_deny"},
    "acr-abac-pull-repair": {"pull"}, "acr-private-data-endpoint": {"pull"},
    "workload-federation-versus-rbac": {"workload_access"},
    "identity-binding-mixed-audiences": {"binding_access", "direct_access"},
    "nap-capacity-control-plane": {"workload"},
    "nap-image-pickup-versus-disruption": {"schedule"},
    "automatic-admission-mutation-quota": {"workload", "effective_resources"},
    "pdb-preserving-upgrade": {"workload"},
    "csi-secret-sync-alias": {"app"}, "csi-rotation-consumption-mode": {"app"},
    "overlay-cidr-exhaustion": {"nodes"},
    "api-connectivity-stage-repair": {"logs"}, "gateway-api-publish": {"http"},
}


def verified(scenario, state):
    w = state["clusters"][0]["_world"]
    diagnostics = {"nap-image-pickup-versus-disruption": {"images", "pdb"}, "pdb-preserving-upgrade": {"upgrade", "pdb"}}.get(scenario["name"], set())
    return diagnostics <= set(w["observations"]) and all(w["observations"].get(tag) == w["generation"] for tag in REQUIRED_OBSERVATIONS[scenario["name"]])
