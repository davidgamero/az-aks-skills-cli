# Configure or repair AKS workload identity

Use for direct Microsoft Entra workload federation with a specified service
account, user-assigned identity and target resource. Reuse existing resources.
Automatic already enables workload identity/OIDC. On Standard, inspect once and
enable only missing features when authorized:

```sh
az aks update -g RG -n CLUSTER --enable-oidc-issuer --enable-workload-identity
```

## Collect the minimum identity tuple

Batch independent reads when their resource names are known:

- Cluster: `az aks show -g RG -n CLUSTER`; retain oidcIssuerProfile.issuerUrl.
- Identity: `az identity show -g IDENTITY_RG -n IDENTITY`; retain clientId and principalId.
- Service account and Deployment template: retain annotation, serviceAccountName,
  pod labels and current authentication error.
- Existing federated credentials on that identity and target-scope role assignments.

## Repair only the missing link

The service account annotation `azure.workload.identity/client-id` uses **clientId**.
For a Deployment, set `spec.template.metadata.labels["azure.workload.identity/use"]`
to the string `"true"` and `spec.template.spec.serviceAccountName` to the intended
service account. Apply the approved manifest with those fields while
preserving image, resources and other configuration.

For an absent direct-federation credential:

```sh
az identity federated-credential create --resource-group "$IDENTITY_RG" --identity-name "$IDENTITY" --name "$FIC_NAME" --issuer "$ISSUER" --subject "system:serviceaccount:$NAMESPACE:$SERVICE_ACCOUNT" --audiences api://AzureADTokenExchange
```

Issuer, subject and audience must match exactly, including case and issuer URL
format. If a selected credential already exists but differs, update that
credential; do not recreate every credential. This is direct federation:
identity-binding tokens use a different audience and require their own flow.

Authentication is separate from target-resource authorization. For an RBAC vault
and an approved vault scope, a missing read permission can be assigned with:

```sh
az role assignment create --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type ServicePrincipal --role "Key Vault Secrets User" --scope "$VAULT_ID"
```

Use the approved role/scope for other services. Management-plane Contributor
alone does not establish data-plane secret access.

## Verify end to end

Template changes trigger rollout; if only service-account annotations changed,
restart the workload once so new pods receive the projected token. Wait for
rollout and execute the intended read using that workload identity, ensuring
another credential cannot mask a broken federation. Report success/status rather
than token or secret contents.
Use a supported Azure Identity SDK; resolve token paths through injected
AZURE_FEDERATED_TOKEN_FILE rather than hard-coding them.

Allow federation/RBAC propagation with bounded retries. A token-exchange mismatch
calls for checking the identity tuple; a resource 403 after token success calls
for authorization/network diagnosis, not rebuilding federation.

Sources:
- https://learn.microsoft.com/en-us/azure/aks/workload-identity-deploy-cluster
- https://learn.microsoft.com/en-us/azure/aks/workload-identity-overview
- https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation
