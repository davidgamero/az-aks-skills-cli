# Repair image pulls at the failing stage

Reuse the exact image and complete pod Events. A token-fetch 401 points toward
authorization; manifest/platform errors require image diagnosis; DNS/TCP/TLS
errors point toward networking. A successful manifest followed by layer timeout
requires the **data endpoint**, not just the login endpoint. A secondary anonymous
401 can follow a platform mismatch; do not assign roles from that line alone.

For authorization, read registry mode and the actual kubelet identity:

```sh
az aks show -g RG -n CLUSTER --query identityProfile.kubeletidentity
az acr show -n REGISTRY
az role assignment list --assignee KUBELET_OBJECT_ID --scope REGISTRY_ID --include-inherited
```

Classic RBAC supports AcrPull/attach-acr. ABAC repository-permissions mode requires
`Container Registry Repository Reader`; AcrPull and attach-acr are insufficient.
For one authorized repository, include the condition rather than granting registry-wide access:

```sh
az role assignment create --assignee-object-id "$KUBELET_OBJECT_ID" --assignee-principal-type ServicePrincipal --role 'Container Registry Repository Reader' --scope "$REGISTRY_ID" --condition-version 2.0 --condition "@Resource[Microsoft.ContainerRegistry/registries/repositories:name] StringEquals '$REPOSITORY'"
```

Reuse existing valid assignments and allow propagation. For network failures,
derive the exact data hostname/private IP from registry configuration and Events.
Check DNS and the affected node-network TCP path; repair only the approved DNS,
route or firewall relationship. Preserve private access and existing permissions.
`az aks check-acr` can help classify reachability but is not a substitute for a
fresh successful pull of the intended image and a Ready rollout.

Sources:
- https://learn.microsoft.com/en-us/troubleshoot/azure/azure-kubernetes/connectivity/cannot-pull-image-from-acr-to-aks-cluster
- https://learn.microsoft.com/en-us/azure/aks/cluster-container-registry-integration
- https://learn.microsoft.com/en-us/azure/container-registry/container-registry-rbac-abac-repository-permissions
