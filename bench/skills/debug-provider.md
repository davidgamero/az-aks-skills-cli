# Recover Automatic creation from missing registration

Use once MissingSubscriptionRegistration identifies the missing namespace.
Automatic needs Microsoft.PolicyInsights for Policy, independently of
Microsoft.ContainerService. If the error is already known, do not repeat
activity-log searches, provider listings, or another failing create to rediscover it.

With registration authorized and the original creation inputs confirmed, run the
complete recovery in one shell call; retain any other required original options:

```sh
az provider register --namespace PROVIDER --wait -o none &&
az aks create -g RG -n CLUSTER --location REGION --sku automatic --enable-hosted-system -o none &&
az aks show -g RG -n CLUSTER
```

The final show verifies Automatic/Standard SKU-tier, hostedSystemProfile.enabled,
Auto provisioning, stable/NodeImage channels and Succeeded. This recipe includes
creation and verification; a second creation skill is unnecessary for this error.

If the failure is still unknown, inspect one relevant failed operation first.
If registration completion is uncertain, query only that provider's state.
--wait already waits; don't add polling after success. An existing cluster or a
different failure requires reassessment. AuthorizationFailed needs permission,
not retries. Do not change SKU, disable managed features, register unrelated
providers or download kubeconfig to verify a management-plane creation.

Sources:
- https://learn.microsoft.com/en-us/azure/azure-resource-manager/troubleshooting/error-register-resource-provider
- https://learn.microsoft.com/en-us/azure/aks/automatic/quick-automatic-managed-network
