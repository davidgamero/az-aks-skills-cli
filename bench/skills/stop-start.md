# Stop or start a development cluster

Use for an authorized power-state change. Reuse recent aks show data; otherwise
read it once. It already includes pool configuration, powerState and provisioningState.
If the requested state is already Succeeded, report that verified state.

For a supported running dev cluster that should be stopped:

```sh
az aks stop -g RG -n CLUSTER &&
az aks show -g RG -n CLUSTER
```

Verify Stopped/Succeeded and preserved configuration from that final response.
For a requested restart, substitute start and verify Running. No independent pool
inventory, credential download or Kubernetes inspection is needed for a
management-plane power-state task unless an error requires it.

Stopping is unsupported with node auto-provisioning. Do not delete the cluster or
zero system pools as a substitute. Start stopped clusters before scale/upgrade.
Allow the documented 15–30 minutes after stopping before a real restart; do not
restart when Stopped is the requested end state.

Source: https://learn.microsoft.com/en-us/azure/aks/start-stop-cluster
