# Repair an ACR image-pull failure

## Identify the failing stage once

Reuse the pod's current Events, or run `kubectl describe pod POD -n NAMESPACE`.
Capture the exact image reference and error; ImagePullBackOff alone is not a cause.

| Evidence | Targeted next step |
|---|---|
| Token-fetch 401 / missing credentials | Check the actual pull identity and effective registry permission |
| Manifest/tag not found or platform mismatch | Check the requested image/tag/digest and node OS/architecture |
| DNS, TCP or TLS failure; some 403 cases | Check the private DNS/egress path from the node network |
| Manifest succeeds but layer download fails | Inspect the data endpoint, not just the login endpoint |

A platform/manifest mismatch can be followed by a secondary anonymous-token 401.
Classify the full error before choosing the authorization branch.

An unauthenticated `/v2/` request returning 401 can demonstrate reachability; it
does not prove kubelet authorization is broken. Use `az aks check-acr -g RG -n
CLUSTER --acr REGISTRY.azurecr.io` when node-side access is uncertain, not as a
replacement for the error evidence.

## Authorization success path

For managed-identity AKS, reuse or read the kubelet identity from
`az aks show -g RG -n CLUSTER --query identityProfile.kubeletidentity`.
Read `az acr show -n REGISTRY` once for registry ID and permission mode; inspect
the kubelet's effective role assignments at that scope.

- Non-ABAC registry: `AcrPull`; `az aks update --attach-acr ACR_ID` supports it.
- ABAC repository-permissions mode: `Container Registry Repository Reader`;
  classic AcrPull and --attach-acr do not provide this integration.

For an authorized missing assignment, use the kubelet **object ID**, not the
control-plane identity. Set ROLE for the registry mode:

```sh
az role assignment create --assignee-object-id "$KUBELET_OBJECT_ID" --assignee-principal-type ServicePrincipal --role "$ROLE" --scope "$ACR_ID"
```

For repository-restricted access, include the approved ABAC condition and
condition version; do not broaden existing scope. Reuse an effective assignment
instead of creating duplicates. Allow role propagation with bounded retries.

## Verify and stop

Verify a fresh successful pull of the intended image and workload readiness
(`kubectl rollout status deployment/DEPLOYMENT -n NAMESPACE` for a Deployment).
Keep the image, registry network restrictions and unrelated roles unchanged.
After fixing authorization, do not rotate credentials, reimage nodes or run a
separate network investigation unless the next error points there. If the role
was already correct, follow the evidence branch rather than adding privileges.

Sources:
- https://learn.microsoft.com/en-us/troubleshoot/azure/azure-kubernetes/connectivity/cannot-pull-image-from-acr-to-aks-cluster
- https://learn.microsoft.com/en-us/azure/aks/cluster-container-registry-integration
- https://learn.microsoft.com/en-us/azure/architecture/operator-guides/aks/aks-triage-container-registry
