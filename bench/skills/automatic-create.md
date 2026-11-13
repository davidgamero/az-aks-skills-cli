# Create an AKS Automatic cluster

Use for new Automatic creation when names, region and prerequisites are known.
Automatic is the SKU; Standard is its tier. `--tier standard` alone creates Base.
With CLI 2.86.0+, execute the synchronous creation and one final read together:

```sh
az aks create -g RG -n CLUSTER --location REGION --sku automatic --enable-hosted-system -o none &&
az aks show -g RG -n CLUSTER
```

Verify SKU Automatic/Standard, hostedSystemProfile.enabled, nodeProvisioningProfile.mode
Auto, upgradeChannel stable, nodeOSUpgradeChannel NodeImage and Succeeded. Managed
networking and these defaults are preconfigured; don't enable them again with
separate updates or add a manually sized pool.

Trust explicitly supplied prerequisite facts and reuse recent checks. Otherwise
check only the missing prerequisite: existing resource group, supported region,
or required provider registration. Don't repeat broad inventories. For
MissingSubscriptionRegistration, register the namespace named by the error with
`az provider register --namespace PROVIDER --wait`, then retry the original create
and final show. Registration requires permission. For any different failure,
stop this sequence and diagnose that error.

Cluster configuration verification does not require kubeconfig, node listing or
workload deployment; those are separate tasks, not proof of the pod-readiness SLA.

Sources:
- https://learn.microsoft.com/en-us/azure/aks/automatic/quick-automatic-managed-network
- https://learn.microsoft.com/en-us/azure/aks/intro-aks-automatic
