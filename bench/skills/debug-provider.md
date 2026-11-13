# Recover Automatic creation from missing registration

`MissingSubscriptionRegistration` identifies a provider namespace that is not
registered. Automatic enables Azure Policy, so Microsoft.PolicyInsights must be
registered even if the cluster resource itself uses Microsoft.ContainerService.

Read the exact error and inspect that namespace:

```sh
az provider show --namespace PROVIDER --query registrationState -o tsv
az provider register --namespace PROVIDER --wait
```

Registration requires subscription-level permission. Once registered, retry the
original `az aks create ... --sku automatic --enable-hosted-system` and verify
the cluster with `az aks show`. Do not change SKU, disable required features, or
register unrelated providers merely to suppress the error. A registration failure
with AuthorizationFailed is a permission issue, not a reason to loop retries.

Sources:
- https://learn.microsoft.com/en-us/azure/azure-resource-manager/troubleshooting/error-register-resource-provider
- https://learn.microsoft.com/en-us/azure/aks/automatic/quick-automatic-managed-network
