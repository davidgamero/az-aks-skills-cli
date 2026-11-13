# Recover exhausted Overlay pod address space

Read networkProfile, node OS/network conditions and NodeNetworkConfig errors.
Distinguish Overlay per-node pod address blocks from VNet subnet addresses and VM
quota. Compute capacity from the current pod CIDR and per-node block size.

Validate the published Linux IPv4 Overlay eligibility, a larger contiguous
superset of the original pod range and the approved address plan. Check service,
VNet and connected ranges for overlap. Preserve existing addresses.

```sh
az aks update -g RG -n CLUSTER --pod-cidr APPROVED_LARGER_SUPERSET
az aks show -g RG -n CLUSTER --query networkProfile
kubectl get nnc -A -o yaml
kubectl get nodes -o wide
```

Verify NNC reconciliation and Ready capacity rather than stopping at ARM success.
An unrelated range, shrink or unsupported OS/address-family combination needs a
different plan; it is not repaired by forcing the same expansion command.

Sources:
- https://learn.microsoft.com/en-us/azure/aks/azure-cni-overlay-pod-expand
- https://learn.microsoft.com/en-us/troubleshoot/azure/azure-kubernetes/extensions/troubleshoot-node-auto-provision
