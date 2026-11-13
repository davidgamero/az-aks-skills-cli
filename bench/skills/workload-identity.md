# Repair the broken workload identity relationship

Classify token acquisition separately from target-resource access. Token-exchange
issuer/subject/audience errors call for the exact federation tuple; a resource 403
after successful exchange calls for resource authorization/network diagnosis.

Read the cluster OIDC issuer, intended managed identity, service account, Deployment
template and selected federated credential. The service-account annotation uses
the identity **clientId**; role assignment uses **principalId**. The pod template
needs `azure.workload.identity/use: "true"` and the correct serviceAccountName.
Automatic enables cluster-level OIDC/workload identity already.

Compare direct federation against:

- Exact cluster `oidcIssuerProfile.issuerUrl`.
- `system:serviceaccount:NAMESPACE:SERVICE_ACCOUNT` subject.
- `api://AzureADTokenExchange` audience.

Update only the differing selected credential:

```sh
az identity federated-credential update -g IDENTITY_RG --identity-name IDENTITY -n FIC --issuer ISSUER --subject system:serviceaccount:NAMESPACE:SERVICE_ACCOUNT --audiences api://AzureADTokenExchange
```

If federation is already correct, inspect the approved data-plane role/scope;
management Contributor does not imply secret access. Preserve working roles and
credentials. Template changes roll out; service-account-only changes may require
one restart so pods receive mutation. Use a supported SDK with the projected token
file, then verify the approved operation **from the workload**, returning status
or version metadata rather than secret/token contents. Allow bounded propagation.

Sources:
- https://learn.microsoft.com/en-us/azure/aks/workload-identity-deploy-cluster
- https://learn.microsoft.com/en-us/azure/aks/workload-identity-overview
