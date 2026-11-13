# Recover an upgrade blocked by a Pod Disruption Budget

Use when the AKS error identifies a pod eviction/PDB blocker. This "Too Many
Requests" can mean no disruption is allowed, not an ARM throttle solved by retry.
Reuse the named namespace, workload and PDB from the error; avoid cluster-wide
scans when the blocker is already identified.

## Inspect the blocking relationship

In one shell call, read the affected Deployment and PDB. Check that the PDB
selector matches the workload, current ready/desired replicas, minAvailable or
maxUnavailable, and **status.disruptionsAllowed**.

## Prefer a repair that preserves the availability requirement

For an absolute minAvailable budget equal to the healthy replica count, an
authorized temporary extra replica can create headroom without changing the PDB:

```sh
kubectl scale deployment/DEPLOYMENT -n NAMESPACE --replicas=TEMPORARY_COUNT &&
kubectl rollout status deployment/DEPLOYMENT -n NAMESPACE --timeout=TIMEOUT &&
kubectl get pdb PDB_NAME -n NAMESPACE -o json
```

Choose TEMPORARY_COUNT from the availability floor and approved capacity. Verify
disruptionsAllowed is positive before retrying the original AKS upgrade scope
and target. Do not assume one extra replica works for every budget: minAvailable
100% and maxUnavailable 0 can remain blocking. If the extra pod cannot become
Ready, diagnose that condition first.

If capacity cannot provide headroom, change the budget only within the workload's
approved availability policy; otherwise report the blocker. Deleting PDBs, force
eviction or scaling to zero are not interchangeable with preserving availability.

## Complete and verify

Retry the original cluster or pool upgrade after the blocker is removed. Verify
the target version, Succeeded provisioning and workload readiness. Restore any
temporary replica change when requested, and verify the original PDB and final
replica count. Do not broaden a pool-only upgrade to the whole cluster.

Batch known dependent operations with &&, but keep the observation of a positive
disruption budget between capacity repair and retry. Stop on a new failure rather
than repeatedly changing unrelated settings.

Sources:
- https://learn.microsoft.com/en-us/troubleshoot/azure/azure-kubernetes/create-upgrade-delete/error-code-poddrainfailure
- https://learn.microsoft.com/en-us/azure/aks/operator-best-practices-scheduler
