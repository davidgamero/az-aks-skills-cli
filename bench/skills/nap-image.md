# Separate NAP image pickup and node replacement

The node OS maintenance window controls when NAP picks up a new image. NodeClaim
drift and node/pod disruption budgets govern replacement. Changing an ordinary
NodeImage channel alone does not resolve a blocked drain.

Read the current schedule and image/drift state. Configure only the authorized
node OS schedule, retaining unrelated maintenance:

```sh
az aks maintenanceconfiguration update -g RG --cluster-name CLUSTER -n aksManagedNodeOSUpgradeSchedule --schedule-type Weekly --day-of-week DAY --interval-weeks 1 --duration HOURS --start-time HH:MM --utc-offset OFFSET
```

Use `add` when absent; use at least a four-hour window and allow the documented
reconciliation lead time (at least 30 minutes). Inspect NodePool disruption budgets
and selected workload PDB status. A drifted NodeClaim plus zero disruptionsAllowed
is evidence that image availability and replacement eligibility differ.

Verify the schedule and actual image/drift/PDB state. If budgets must remain intact,
report the exact remaining blocker rather than deleting budgets or promising all
nodes will roll at the window boundary. Window closure is not a guarantee that
all in-flight disruption is canceled.

Sources:
- https://learn.microsoft.com/en-us/azure/aks/node-auto-provisioning-upgrade-image
- https://learn.microsoft.com/en-us/azure/aks/node-auto-provisioning-node-pools
