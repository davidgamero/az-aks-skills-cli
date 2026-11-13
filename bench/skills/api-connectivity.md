# Identify the failing API operation path

Start from operations that already work. Successful `kubectl get` establishes
more than a failed logs/exec call alone. Compare raw API/read behavior, logs/exec
errors and operation-specific authorization.

- DNS/TCP/TLS failure before any API response: investigate client-to-API path.
- 401: API is reachable but authentication is not established.
- Forbidden: inspect the intended principal's operation-specific permission.
- Reads work, logs/exec timeout: investigate API-server-to-kubelet/tunnel path,
  including the required TCP 10250 path in the applicable architecture.

Read the AKS access profile and only the implicated customer-owned network
controls. Preserve endpoint exposure and client authorized ranges. Repair the
approved narrow rule rather than opening public API access, retrieving admin
credentials or editing AKS-managed infrastructure without support.

Verify the previously failing logs/exec operation and that ordinary reads still
work. Preserve unrelated rules, identities and scopes. Reuse observed resource
identifiers rather than guessing node resource-group ownership.

Sources:
- https://learn.microsoft.com/en-us/troubleshoot/azure/azure-kubernetes/connectivity/troubleshoot-cluster-connection-issues-api-server
- https://learn.microsoft.com/en-us/azure/aks/network-policy-best-practices
