"""Seeded primary fixtures for the 17 researched candidates. Oracles live separately."""

import copy
import json
from pathlib import Path

PLAN = json.loads((Path(__file__).resolve().parents[2] / "docs/research/scenario-candidates.json").read_text())
DEFINITIONS = {c["id"]: c for c in PLAN["candidates"]}
NAMES = tuple(DEFINITIONS)


def key(kind, namespace, name):
    return f"{kind.lower()}|{namespace or ''}|{name}"


def obj(kind, name, namespace="retail", spec=None, **extra):
    api = {"Deployment": "apps/v1", "NetworkPolicy": "networking.k8s.io/v1", "PodDisruptionBudget": "policy/v1",
           "NodePool": "karpenter.sh/v1", "NodeClaim": "karpenter.sh/v1", "AKSNodeClass": "karpenter.azure.com/v1beta1",
           "SecretProviderClass": "secrets-store.csi.x-k8s.io/v1", "Gateway": "gateway.networking.k8s.io/v1",
           "HTTPRoute": "gateway.networking.k8s.io/v1", "GatewayClass": "gateway.networking.k8s.io/v1"}.get(kind, "v1")
    metadata = {"name": name, "uid": f"initial-{kind.lower()}-{namespace}-{name}"}
    if namespace:
        metadata["namespace"] = namespace
    result = {"apiVersion": api, "kind": kind, "metadata": metadata, **extra}
    if spec is not None:
        result["spec"] = spec
    return result


def put(world, resource):
    m = resource["metadata"]
    world["resources"][key(resource["kind"], m.get("namespace", ""), m["name"])] = resource
    return resource


def make(name, seed, base):
    s = copy.deepcopy(base)
    c = s["state"]["clusters"][0]
    suffix = c["name"].rsplit("-", 1)[1]
    ns = "retail"
    subscription = "00000000-0000-0000-0000-000000000001"
    identity_id = f"/subscriptions/{subscription}/resourceGroups/{c['resourceGroup']}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/app-id"
    registry_id = f"/subscriptions/{subscription}/resourceGroups/{c['resourceGroup']}/providers/Microsoft.ContainerRegistry/registries/registry{suffix}"
    vault_id = f"/subscriptions/{subscription}/resourceGroups/{c['resourceGroup']}/providers/Microsoft.KeyVault/vaults/vault{suffix}"
    developer = f"00000000-0000-0000-0000-{int(suffix):012d}"
    image = f"registry{suffix}.azurecr.io/team/api:v2"
    c.update(sku={"name": "Base", "tier": "Standard"},
             enableRbac=True, aadProfile={"managed": True, "enableAzureRbac": True},
             identityProfile={"kubeletidentity": {"objectId": "kubelet-principal", "clientId": "kubelet-client"}},
             oidcIssuerProfile={"enabled": True, "issuerUrl": f"https://eastus.oic.prod-aks.azure.com/tenant/{suffix}/"},
             securityProfile={"workloadIdentity": {"enabled": True}},
             apiServerAccessProfile={"enablePrivateCluster": True, "enableVnetIntegration": False, "authorizedIpRanges": ["198.51.100.10/32"]},
             fqdn="api.example.test", privateFqdn="api.private.example.test",
             networkProfile={"networkPlugin": "azure", "networkPluginMode": "overlay", "networkDataplane": "cilium",
                             "podCidr": "10.244.0.0/16", "serviceCidr": "10.100.0.0/16", "dnsServiceIp": "10.100.0.10"})
    w = {"resources": {}, "managed_namespaces": {}, "roles": [], "violations": [], "generation": 0,
         "node_ready": True, "context": c["name"], "secret_source_version": "version-2",
         "app_secret_version": "version-2", "probe_history": [], "observations": {},
         "identities": {"app-id": {"id": identity_id, "name": "app-id", "clientId": "app-client", "principalId": "app-principal", "tenantId": "tenant"}},
         "federated_credentials": [{"name": "app-fic", "issuer": c["oidcIssuerProfile"]["issuerUrl"],
                                     "subject": "system:serviceaccount:retail:app-sa", "audiences": ["api://AzureADTokenExchange"]}],
         "registry": {"id": registry_id, "name": f"registry{suffix}", "loginServer": f"registry{suffix}.azurecr.io",
                      "roleAssignmentMode": "AbacRepositoryPermissions", "publicNetworkAccess": "Disabled",
                      "dataEndpointHostNames": [f"registry{suffix}.eastus.data.azurecr.io"]},
         "vault": {"id": vault_id, "name": f"vault{suffix}", "properties": {"enableRbacAuthorization": True, "vaultUri": f"https://vault{suffix}.vault.azure.net/"}},
         "nsg": {"id": f"/subscriptions/{subscription}/resourceGroups/network-rg/providers/Microsoft.Network/networkSecurityGroups/app-network",
                 "name": "app-network", "resourceGroup": "network-rg", "securityRules": [
                     {"name": "required-path", "access": "Allow", "direction": "Outbound", "protocol": "Tcp", "priority": 200,
                      "sourceAddressPrefix": "10.0.1.0/24", "destinationAddressPrefix": "10.0.2.5/32",
                      "sourcePortRange": "*", "destinationPortRange": "443"}]},
         "safeguards": {"level": "Enforce", "excludedNamespaces": []},
         "maintenance": {}, "clock": "2026-11-15T01:30:00Z", "minimum_ready_seen": 2}
    c["_world"] = w
    private_endpoint_id = f"/subscriptions/{subscription}/resourceGroups/network-rg/providers/Microsoft.Network/privateEndpoints/registry-private"
    w["private_endpoint"] = {"id": private_endpoint_id, "name": "registry-private", "resourceGroup": "network-rg",
        "type": "Microsoft.Network/privateEndpoints", "provisioningState": "Succeeded",
        "customDnsConfigs": [{"fqdn": hostname, "ipAddresses": ["10.0.2.5"]} for hostname in [w["registry"]["loginServer"], *w["registry"]["dataEndpointHostNames"]]]}
    w["registry"]["privateEndpointConnections"] = [{"name": "registry-private", "privateEndpoint": {"id": private_endpoint_id},
        "privateLinkServiceConnectionState": {"status": "Approved"}}]
    c["addonProfiles"] = {"azureKeyvaultSecretsProvider": {"enabled": True,
        "config": {"enableSecretRotation": "true", "rotationPollInterval": "2m"}}}
    for namespace in (ns, "ingress", "other", "kube-system"):
        r = put(w, obj("Namespace", namespace, ""))
        r["metadata"].update(labels={"kubernetes.io/metadata.name": namespace, "team": namespace}, annotations={"owner": "platform"})
    deployment = put(w, obj("Deployment", "api", ns, {"replicas": 2, "selector": {"matchLabels": {"app": "api"}},
        "template": {"metadata": {"labels": {"app": "api", "azure.workload.identity/use": "true"}}, "spec": {
            "serviceAccountName": "app-sa", "containers": [{"name": "api", "image": image,
              "resources": {"requests": {"cpu": "200m", "memory": "256Mi"}, "limits": {"cpu": "500m", "memory": "512Mi"}},
              "readinessProbe": {"httpGet": {"path": "/ready", "port": 8080}},
              "env": [{"name": "DIRECT_FIC_TOKEN_FILE", "value": "/var/run/binding/token"}]}],
            "volumes": [{"name": "binding-token", "projected": {"sources": [{"serviceAccountToken": {"path": "token", "audience": "api://AKSIdentityBinding"}}]}}]}}}))
    deployment["spec"]["template"]["spec"]["containers"][0]["volumeMounts"] = [{"name": "binding-token", "mountPath": "/var/run/binding", "readOnly": True}]
    put(w, obj("Service", "api", ns, {"type": "ClusterIP", "clusterIP": "10.100.0.20", "selector": {"app": "api"}, "ports": [{"port": 8080, "targetPort": 8080}]}))
    put(w, obj("PersistentVolumeClaim", "data", ns, {"accessModes": ["ReadWriteOnce"], "resources": {"requests": {"storage": "1Gi"}}}, status={"phase": "Bound", "dataVersion": "unchanged-data"}))
    sa = put(w, obj("ServiceAccount", "app-sa", ns))
    sa["metadata"]["annotations"] = {"azure.workload.identity/client-id": "app-client"}
    quota = put(w, obj("ResourceQuota", "managed-quota", ns, {"hard": {"requests.cpu": "4000m", "limits.cpu": "8000m", "requests.memory": "2Gi", "limits.memory": "4Gi"}}))
    policy = put(w, obj("NetworkPolicy", "managed-ingress", ns, {"podSelector": {}, "policyTypes": ["Ingress"],
        "ingress": [{"from": [{"podSelector": {}}]}]}))
    namespace_arm = {"id": c["id"] + f"/managedNamespaces/{ns}", "name": ns, "location": c["location"], "resourceGroup": c["resourceGroup"],
        "provisioningState": "Succeeded", "defaultResourceQuota": {"cpuRequest": "4000m", "cpuLimit": "8000m", "memoryRequest": "2Gi", "memoryLimit": "4Gi"},
        "defaultNetworkPolicy": {"ingress": "AllowSameNamespace", "egress": "AllowAll"},
        "adoptionPolicy": "IfIdentical", "deletePolicy": "Delete", "labels": {"team": ns}, "annotations": {"owner": "platform"}}
    w["managed_namespaces"][ns] = namespace_arm
    w["resources"][key("Namespace", "", ns)]["metadata"]["labels"]["ManagedByARM"] = "true"
    w["roles"] = [{"principalId": developer, "roleDefinitionName": "Azure Kubernetes Service Namespace User", "scope": namespace_arm["id"]},
                  {"principalId": "app-principal", "roleDefinitionName": "Key Vault Secrets User", "scope": vault_id},
                  {"principalId": "kubelet-principal", "roleDefinitionName": "Container Registry Repository Reader", "scope": registry_id,
                   "condition": "@Resource[Microsoft.ContainerRegistry/registries/repositories:name] StringEquals 'team/api'"}]
    for pool in c["agentPoolProfiles"]:
        for i in range(pool["count"]):
            put(w, obj("Node", f"{pool['name']}-{i}", "", {"podCIDR": f"10.244.{len([r for r in w['resources'].values() if r['kind']=='Node'])}.0/24"},
                       status={"conditions": [{"type": "Ready", "status": "True"}], "nodeInfo": {"kubeletVersion": "v"+pool["orchestratorVersion"]}}))
            w["resources"][key("node", "", f"{pool['name']}-{i}")]["metadata"]["labels"] = {"agentpool": pool["name"], "kubernetes.azure.com/agentpool": pool["name"]}
    nap = put(w, obj("NodePool", "workers", "", {"template": {"spec": {"nodeClassRef": {"group": "karpenter.azure.com", "kind": "AKSNodeClass", "name": "default"},
        "requirements": [{"key": "kubernetes.io/arch", "operator": "In", "values": ["amd64"]}], "taints": []}},
        "limits": {"cpu": "4"}, "disruption": {"budgets": [{"nodes": "1"}], "consolidationPolicy": "WhenEmptyOrUnderutilized"}},
        status={"resources": {"cpu": "4"}, "conditions": [{"type": "Ready", "status": "True"}]}))
    put(w, obj("AKSNodeClass", "default", "", {"imageFamily": "AzureLinux"}, status={"conditions": [{"type": "Ready", "status": "True"}]}))
    put(w, obj("NodeClaim", "workers-1", "", {"nodeClassRef": {"name": "default"}}, status={"imageID": "image-v1", "conditions": [{"type": "Drifted", "status": "True", "reason": "NewImageAvailable"}]}))
    pdb = put(w, obj("PodDisruptionBudget", "api-pdb", ns, {"minAvailable": 2, "selector": {"matchLabels": {"app": "api"}}}))
    spc = put(w, obj("SecretProviderClass", "app-secrets", ns, {"provider": "azure", "parameters": {
        "keyvaultName": f"vault{suffix}", "clientID": "app-client", "objects": "array:\n  - |\n    objectName: backend-key\n    objectType: secret\n    objectAlias: app-key\n"},
        "secretObjects": [{"secretName": "app-secret", "type": "Opaque", "data": [{"key": "config", "objectName": "app-key"}]}]}))
    secret = put(w, obj("Secret", "app-secret", ns, data={"config": "c3ludGhldGljLXZlcnNpb24tMg=="}, type="Opaque"))
    secret["metadata"]["annotations"] = {"source-version": "version-2", "managed-by": "secrets-store-csi"}
    context = {"cluster": c["name"], "resource_group": c["resourceGroup"], "namespace": ns, "deployment": "api",
        "developer_object_id": developer, "approved_namespace_scope": namespace_arm["id"], "registry": w["registry"]["name"],
        "registry_id": registry_id, "repository": "team/api", "approved_image": image, "identity": "app-id", "identity_resource_group": c["resourceGroup"],
        "vault_id": vault_id, "approved_temporary_replicas": 3, "availability_floor": 2, "approved_nap_cpu_ceiling": "8",
        "approved_pod_cidr": "10.244.0.0/20", "network_resource_group": "network-rg", "nsg": "app-network",
        "approved_hostname": "api.example.test", "approved_path": "/api", "service_port": 8080,
        "approved_resources": {"requests": {"cpu": "200m", "memory": "256Mi"}, "limits": {"cpu": "500m", "memory": "512Mi"}},
        "approved_image_schedule": {"day": "Sunday", "start": "01:00", "duration_hours": 4, "utc_offset": "+00:00"}}
    context["application_probe"] = "kubectl exec -n retail deployment/api -- /app/probe --all"
    context["traffic_probes"] = {"approved_source": "ingress/controller-0", "unrelated_source": "other/probe", "url": "http://api.retail.svc.cluster.local:8080/health"}
    if name == "managed-namespace-adopt-identical":
        w["managed_namespaces"] = {}
        w["resources"][key("Namespace", "", ns)]["metadata"]["labels"].pop("ManagedByARM")
    if name in ("acr-abac-pull-repair", "acr-private-data-endpoint"):
        w["pull_required"] = True
        if name == "acr-private-data-endpoint":
            w["nsg"]["securityRules"][0]["access"] = "Deny"
        else:
            w["roles"][-1].update(roleDefinitionName="AcrPull")
            w["roles"][-1].pop("condition", None)
    if name == "workload-federation-versus-rbac":
        w["federated_credentials"][0]["subject"] = "system:serviceaccount:wrong:app-sa"
    if name == "identity-binding-mixed-audiences":
        deployment["spec"]["template"]["metadata"]["annotations"] = {"azure.workload.identity/use-identity-binding": "true"}
        w["federated_credentials"][0]["subject"] = f"system:serviceaccount:{ns}:app-sa"
        w["federated_credentials"].append({"name": "aks-identity-binding", "issuer": "https://ib.oic.prod-aks.azure.com/tenant/app-client", "subject": "binding-managed", "audiences": ["api://AKSIdentityBinding"]})
        w["identity_binding"] = {"name": "app-binding", "managedIdentityResourceId": identity_id, "provisioningState": "Succeeded"}
        w["sdk"] = {"package": "azure-identity", "version": "1.26.0b2", "credential": "WorkloadIdentityCredential", "enable_azure_proxy": True}
    if name == "nap-capacity-control-plane":
        c["nodeProvisioningProfile"] = {"mode": "Auto"}
        deployment["spec"]["replicas"] = 3
        deployment["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"]["cpu"] = "2"
        deployment["spec"]["template"]["spec"]["nodeSelector"] = {"karpenter.sh/nodepool": "workers"}
        nap["spec"]["template"]["spec"]["requirements"].append({"key": "karpenter.azure.com/sku-name", "operator": "In", "values": ["Standard_D4s_v5"]})
        w["resources"][key("nodeclaim", "", "workers-1")]["status"] = {"imageID": "image-v2", "capacity": {"cpu": "4"}, "conditions": [{"type": "Ready", "status": "True"}]}
        node = put(w, obj("Node", "workers-1", "", {"podCIDR": "10.244.20.0/24"}, status={"capacity": {"cpu": "4"}, "conditions": [{"type": "Ready", "status": "True"}]}))
        node["metadata"]["labels"] = {"karpenter.sh/nodepool": "workers"}
    if name == "nap-image-pickup-versus-disruption":
        c["nodeProvisioningProfile"] = {"mode": "Auto"}
        w["image_blocked"] = True  # Preserve the zero-disruption PDB; diagnose it, do not bypass it.
        context["operation_goal"] = "configure schedule and diagnose remaining replacement blocker"
        context["approved_changes"] = "image maintenance schedule only; retain workload replica count and node/pod disruption budgets"
    if name == "automatic-admission-mutation-quota":
        c["sku"]["name"] = "Automatic"
        c["nodeProvisioningProfile"] = {"mode": "Auto"}
        c["autoUpgradeProfile"] = {"upgradeChannel": "stable", "nodeOSUpgradeChannel": "NodeImage"}
        deployment["spec"]["replicas"] = 4
        deployment["spec"]["template"]["spec"]["containers"][0]["resources"] = {}
    if name == "pdb-preserving-upgrade":
        c["kubernetesVersion"] = c["currentKubernetesVersion"] = "1.34.2"
        c["agentPoolProfiles"][1]["provisioningState"] = "Failed"
        context["target_version"] = "1.34.2"
    if name == "csi-secret-sync-alias":
        spc["spec"]["secretObjects"][0]["data"][0]["objectName"] = "wrong-alias"
        del w["resources"][key("Secret", ns, "app-secret")]
        deployment["spec"]["template"]["spec"]["volumes"].append({"name": "secrets", "csi": {"driver": "secrets-store.csi.k8s.io", "volumeAttributes": {"secretProviderClass": "app-secrets"}}})
        deployment["spec"]["template"]["spec"]["containers"][0]["volumeMounts"].append({"name": "secrets", "mountPath": "/mnt/secrets", "readOnly": True})
        deployment["spec"]["template"]["spec"]["containers"][0]["env"].append({"name": "APP_CONFIG", "valueFrom": {"secretKeyRef": {"name": "app-secret", "key": "config"}}})
    if name == "csi-rotation-consumption-mode":
        w["app_secret_version"] = "version-1"
        spc["spec"]["secretObjects"][0]["data"][0]["objectName"] = "app-key"
        w["rotation_interval"] = "2m"
        deployment["spec"]["template"]["spec"]["containers"][0]["env"].append({"name": "APP_CONFIG", "valueFrom": {"secretKeyRef": {"name": "app-secret", "key": "config"}}})
        deployment["spec"]["template"]["spec"]["volumes"].append({"name": "secrets", "csi": {"driver": "secrets-store.csi.k8s.io", "volumeAttributes": {"secretProviderClass": "app-secrets"}}})
        deployment["spec"]["template"]["spec"]["containers"][0]["volumeMounts"].append({"name": "secrets", "mountPath": "/mnt/secrets", "readOnly": True})
        context["application_configuration"] = {"supported_input": "APP_CONFIG environment variable from app-secret/config", "supports_file_reload": False, "recovery_goal": "one-time refresh using the current application contract"}
        put(w, obj("SecretProviderClassPodStatus", "api-0-app-secrets", ns, status={"mounted": True, "objects": [{"id": "secret/backend-key", "version": "version-2"}]}))
    if name == "overlay-cidr-exhaustion":
        c["networkProfile"]["podCidr"] = "10.244.0.0/22"
        w["overlay_pending"] = True
    if name == "api-connectivity-stage-repair":
        w["nsg"]["securityRules"][0].update(access="Deny", direction="Inbound", sourceAddressPrefix="10.0.0.0/28", destinationAddressPrefix="10.0.1.0/24", destinationPortRange="10250")
    if name == "gateway-api-publish":
        c["sku"]["name"] = "Automatic"
        c["kubernetesVersion"] = c["currentKubernetesVersion"] = "1.36.0"
        c["ingressProfile"] = {"gatewayAPI": {"installation": "Standard"}, "webAppRouting": {"gatewayAPIImplementations": {"appRoutingIstio": {"mode": "Enabled"}}}}
        put(w, obj("GatewayClass", "approuting-istio", "", {"controllerName": "istio.io/gateway-controller"}, status={"conditions": [{"type": "Accepted", "status": "True"}]}))
        w["old_route_healthy"] = True
        put(w, obj("Gateway", "existing-gw", ns, {"gatewayClassName": "approuting-istio", "listeners": [{"name": "http", "port": 80, "protocol": "HTTP"}]}))
        put(w, obj("HTTPRoute", "existing-route", ns, {"parentRefs": [{"name": "existing-gw"}], "hostnames": ["legacy.example.test"],
               "rules": [{"matches": [{"path": {"type": "PathPrefix", "value": "/old"}}], "backendRefs": [{"name": "api", "port": 8080}]}]}))
        context["existing_hostname"] = "legacy.example.test"
    if name != "pdb-preserving-upgrade": context.pop("approved_temporary_replicas")
    if name != "nap-capacity-control-plane": context.pop("approved_nap_cpu_ceiling")
    s.update(name=name, seed=seed, suite="candidate-v1", variant="primary", fault_model="bounded-stateful",
             context=context, candidate=DEFINITIONS[name], faults=[], responses=[])
    s["prompt"] = DEFINITIONS[name]["prompt"].format(namespace=ns, service="api", image=image, workload="api")
    s["prompt"] += (f" Operate on cluster {c['name']} in resource group {c['resourceGroup']}. "
                    "Authorized resource identifiers and limits are in /work/task-context.json. "
                    "kubectl is configured and the CLI is authenticated. Carry out the task and verify the outcome.")
    s["workspace_files"] = {"task-context.json": json.dumps(context, indent=2), "workload.yaml": json.dumps(deployment, indent=2),
                            "secret-provider-class.yaml": json.dumps(spc, indent=2)}
    from .candidate_runtime import World
    World(s, s["state"]).reconcile()
    s["expected"] = {"namespace": copy.deepcopy(namespace_arm), "deployment": copy.deepcopy(deployment),
                     "quota": copy.deepcopy(quota), "policy": copy.deepcopy(policy), "pdb": copy.deepcopy(pdb),
                     "cluster_public": {k:copy.deepcopy(v) for k,v in c.items() if not k.startswith("_")},
                     "roles": copy.deepcopy(w["roles"]), "nsg": copy.deepcopy(w["nsg"]), "resource_uids": {k:r["metadata"]["uid"] for k,r in w["resources"].items()},
                     "fic": copy.deepcopy(w["federated_credentials"])}
    s["initial_state"] = copy.deepcopy(s["state"])
    return s
