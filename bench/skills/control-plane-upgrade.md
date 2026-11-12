# Upgrade only the control plane

Read `az aks show -g RG -n CLUSTER` to capture the control plane and agentPoolProfiles
versions. Check eligible targets using `az aks get-upgrades -g RG -n CLUSTER`.
Do not assume the newest regional version is a valid direct upgrade target.

For a control-plane-only request, use:

```sh
az aks upgrade -g RG -n CLUSTER --kubernetes-version VERSION --control-plane-only --yes
```

Omitting --control-plane-only also upgrades node pools. Control-plane-only upgrades
are incompatible with cluster autoupgrade. For supported non-LTS clusters, don't
skip minor versions. Node pools must not be newer than the control plane.

Verify kubernetesVersion and provisioningState with aks show, and compare the
agentPoolProfiles versions with the initial versions. The synchronous command
waits for completion; --no-wait requires a later wait or polling.

Source: https://learn.microsoft.com/en-us/azure/aks/upgrade-aks-control-plane
