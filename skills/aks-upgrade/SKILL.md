# Plan an AKS upgrade

Use this skill to gather the information needed for a Kubernetes version upgrade.
Replace the example variables with the target cluster and resource group.

1. Inspect the cluster's current version and configuration:
   `az aks show --resource-group "$RESOURCE_GROUP" --name "$CLUSTER" -o json`.
2. Discover supported upgrade targets:
   `az aks get-upgrades --resource-group "$RESOURCE_GROUP" --name "$CLUSTER" -o table`.
3. Inventory node pools:
   `az aks nodepool list --resource-group "$RESOURCE_GROUP" --cluster-name "$CLUSTER" -o table`.
4. Review deprecated Kubernetes APIs, workload compatibility, pod disruption
   budgets, surge capacity, and the maintenance window for the target version.
5. Produce a plan covering control-plane and node-pool sequencing, validation,
   and workload recovery. Do not assume a Kubernetes downgrade is available.

Expected output: current versions, available targets, compatibility findings,
and a proposed upgrade sequence.
