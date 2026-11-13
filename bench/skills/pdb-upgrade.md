# Recover an upgrade without weakening availability

Reuse the named pod/Deployment/PDB from the upgrade error. Eviction TooManyRequests
can mean no permitted disruption, not an ARM throttle. Read the selector, healthy
replicas, minAvailable/maxUnavailable and status.disruptionsAllowed together.

For an absolute minAvailable equal to healthy replicas, approved extra Ready
replicas may create headroom:

```sh
kubectl scale deployment/DEPLOYMENT -n NAMESPACE --replicas=APPROVED_TEMPORARY_COUNT
kubectl rollout status deployment/DEPLOYMENT -n NAMESPACE --timeout=TIMEOUT
kubectl get pdb PDB_NAME -n NAMESPACE -o json
```

Verify positive disruption allowance before retrying the original pool upgrade
scope/target. Extra replicas cannot solve every percentage or zero-unavailability
budget; if a new pod cannot become Ready, diagnose that first. Preserve the PDB
throughout; deleting and recreating it does not preserve the temporal requirement.

After the target pool reaches the requested version and Succeeded state, restore
the original replica count, verify readiness and unchanged PDB. Keep unrelated
pools and capacity settings intact. If approved headroom is insufficient, report
the availability constraint instead of forcing eviction.

Sources:
- https://learn.microsoft.com/en-us/troubleshoot/azure/azure-kubernetes/create-upgrade-delete/error-code-poddrainfailure
- https://learn.microsoft.com/en-us/azure/aks/operator-best-practices-scheduler
