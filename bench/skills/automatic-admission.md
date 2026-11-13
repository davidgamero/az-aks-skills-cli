# Diagnose submitted versus admitted resources on Automatic

Compare the Deployment template to actual admitted Pod resources, Events and
ResourceQuota usage. Missing resources may be defaulted by Automatic; this can
exhaust a quota even when the submitted manifest looks small. Distinguish mutation,
policy denial and quota denial before adding capacity.

Use the application's approved explicit requests/limits in the template. Preserve
probes, image, placement and replica target; keep safeguards Enforce and the
namespace included. Automatic cannot be switched to Warn as a workaround.

```sh
kubectl get deployment DEPLOYMENT -n NAMESPACE -o yaml
kubectl get pods,resourcequota -n NAMESPACE -o yaml
az aks safeguards show -g RG -n CLUSTER
```

Patch/apply only approved resource fields, then verify **admitted Pods**, quota
usage and the full Ready replica count. Inspecting only the submitted Deployment
does not prove mutation behaved as intended. A fixed quota must not be raised.
Partial-resource mutations depend on the policy version; do not infer them from
fully missing-resource defaults.

Sources:
- https://learn.microsoft.com/en-us/azure/aks/deployment-safeguards
- https://learn.microsoft.com/en-us/azure/aks/intro-aks-automatic
