# Investigate unhealthy AKS pods

Use an existing kubectl context for the target cluster and select a namespace.

1. Confirm the current context with `kubectl config current-context`.
2. List pod states with `kubectl get pods --namespace "$NAMESPACE" -o wide`.
3. Inspect the affected pod with
   `kubectl describe pod "$POD" --namespace "$NAMESPACE"`.
4. Read container logs with
   `kubectl logs "$POD" --namespace "$NAMESPACE" --container "$CONTAINER"`.
   For a restarted container, also request `--previous`.
5. Correlate scheduling events, image pull failures, readiness/liveness failures,
   resource limits, and exit codes before proposing a change.

Expected output: observed symptoms, supporting events or logs, likely cause,
and the next diagnostic or remediation step.
