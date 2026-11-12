# Stop or start a development cluster

Read `az aks show -g RG -n CLUSTER` to inspect powerState and provisioningState.
For an idle development cluster the user wants stopped, use
`az aks stop -g RG -n CLUSTER`, then verify powerState.code is Stopped and
provisioningState is Succeeded. Stopping preserves cluster configuration; deleting
the cluster or scaling system pools to zero does not implement this task.

To restart a stopped cluster use `az aks start -g RG -n CLUSTER` and verify Running.
Start a stopped cluster before attempting scale or upgrade operations. On real AKS,
allow 15–30 minutes after stopping before restarting, and check feature limitations
such as node autoprovisioning. Do not restart a cluster when the requested final
state is stopped.

Source: https://learn.microsoft.com/en-us/azure/aks/start-stop-cluster
