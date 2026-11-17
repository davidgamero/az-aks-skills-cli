# Persistent custom forwarding in AKS CoreDNS

Use when an approved private forwarder works directly but normal pod DNS does not,
or a customization is not imported/persistent. Check whether LocalDNS is involved;
this recipe is for the observed CoreDNS custom-import path.

```sh
kubectl get configmap coredns coredns-custom -n kube-system -o yaml
kubectl logs -n kube-system deployment/coredns --tail=80
```

Do not replace the AKS-managed `coredns` Corefile or remove its cluster resolution
plugins. Preserve unrelated custom keys. AKS imports `custom/*.server` as separate
server blocks and `custom/*.override` within the default block. A key ending in
`.conf` or `.yaml` is not imported by those patterns even if its contents are valid.

For domain-specific forwarding, put the approved block under a `.server` key in
`coredns-custom`, for example:

```yaml
data:
  private.server: |
    PRIVATE_ZONE:53 {
      errors
      cache 30
      forward . APPROVED_UPSTREAM
    }
```

Keep a copy of the old configuration, apply only the custom ConfigMap, and perform
the guide's rolling reload when authorized:

```sh
kubectl apply -f corrected-custom-dns.yaml
kubectl rollout restart deployment/coredns -n kube-system
kubectl rollout status deployment/coredns -n kube-system
```

Verify the original private query **through normal workload DNS**, not just by
explicitly targeting the upstream. Also test cluster service names, an external
name and preserved custom zones. A successful ConfigMap write does not prove a
running DNS process has consumed it. Do not solve this with static pod hostAliases
or by deploying a second resolver unless separately authorized.

Source: https://learn.microsoft.com/en-us/azure/aks/coredns-custom
