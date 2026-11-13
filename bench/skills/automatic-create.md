# Create an AKS Automatic cluster

Use the requested cluster name, existing resource group and location. Automatic
is a **SKU**, while Standard is its pricing **tier**. `--tier standard` alone does
not create an Automatic cluster. With Azure CLI 2.86.0+, use:

```sh
az aks create --resource-group RG --name CLUSTER --location REGION --sku automatic --enable-hosted-system
```

Current new-cluster defaults include managed system pools; the explicit hosted
system flag also states that intent. Managed networking, node auto-provisioning,
stable cluster upgrades and NodeImage node OS upgrades are configured for you.
Don't turn this into a manually sized pool or a cluster-autoscaler configuration.
Avoid redundant update commands to enable features already preconfigured.

Before creation, the required resource providers (including Microsoft.PolicyInsights)
must be registered. If the task states that prerequisites are satisfied, do not
repeat registration or resource-group creation. Use a supported region.

Verify with one `az aks show --resource-group RG --name CLUSTER`, checking:

- sku.name: Automatic; sku.tier: Standard.
- hostedSystemProfile.enabled: true.
- nodeProvisioningProfile.mode: Auto.
- autoUpgradeProfile.upgradeChannel: stable.
- autoUpgradeProfile.nodeOSUpgradeChannel: NodeImage.
- provisioningState: Succeeded.

For a management-plane-only task, downloading kubeconfig and deploying workloads
are unnecessary. A completed create response does not itself demonstrate workload
scheduling or the pod readiness SLA.

Sources:
- https://learn.microsoft.com/en-us/azure/aks/automatic/quick-automatic-managed-network
- https://learn.microsoft.com/en-us/azure/aks/intro-aks-automatic
