# Refresh the stale layer of secret consumption

Compare nonsecret version metadata across source, mounted file/synced Secret and
application-reported configuration. Keep the approved polling interval and identity.
Never print secret/token values for diagnosis.

Environment variables are captured when a pod starts. A current synced Secret
does not refresh an existing process environment. For an authorized one-time
recovery of an env consumer:

```sh
kubectl rollout restart deployment/DEPLOYMENT -n NAMESPACE
kubectl rollout status deployment/DEPLOYMENT -n NAMESPACE --timeout=TIMEOUT
```

For file consumers, use the application's supported reload mechanism; a mounted
file update does not ensure the process rereads it. If the source or CSI layer
is still stale, investigate that layer instead of restarting repeatedly.
Verify the application's version and readiness after refresh. Shortening a poll
interval cannot refresh a process environment that already missed an updated
Secret. Ongoing automatic refresh is a separate application/reloader design task.

Sources:
- https://learn.microsoft.com/en-us/azure/aks/csi-secrets-store-configuration-options
- https://learn.microsoft.com/en-us/troubleshoot/azure/azure-kubernetes/extensions/troubleshoot-key-vault-csi-secrets-store-csi-driver
