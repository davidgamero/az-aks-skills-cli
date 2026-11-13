# Preserve identity bindings while repairing direct federation

Check cluster support, binding state, service-account authorization, SDK version
and proxy opt-in. Identity bindings exclude API-server VNet integration; consult
the pinned SDK support matrix rather than assuming ordinary workload-identity
support is enough. Inspect the pod's actual token projections and client file paths.

A binding token's audience is `api://AKSIdentityBinding`. Direct federation uses
`api://AzureADTokenExchange`. Keep the binding projection, managed FIC and SDK
binding configuration intact. Add a separate projected volume for direct exchange:

```yaml
volumes:
- name: direct-federation-token
  projected:
    sources:
    - serviceAccountToken:
        path: token
        audience: api://AzureADTokenExchange
```

Mount it read-only at a distinct path in the intended container and configure the
direct-federation client to use that file. Merge into existing volumes/mounts/env;
do not replace unrelated arrays or overwrite the shared binding token audience.
Preserve the exact direct FIC issuer/subject/audience and resource permissions.
Roll out and independently verify both approved workload access paths.

Sources:
- https://learn.microsoft.com/en-us/azure/aks/workload-identity-overview
- https://learn.microsoft.com/en-us/azure/aks/identity-bindings-concepts
- https://learn.microsoft.com/en-us/azure/aks/identity-bindings
