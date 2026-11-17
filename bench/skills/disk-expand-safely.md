# Expand an existing Azure Disk CSI volume safely

Read PVC, its bound PV, StorageClass and actual managed disk SKU. Confirm
`allowVolumeExpansion`, current/requested sizes, mount consumers, original replica
count and the approved maintenance policy. Do not infer the disk type from a class
name alone. Preserve the CSI volumeHandle, disk identity, claim and data.

The documented AKS resize procedure distinguishes these cases:

- Standard HDD, Standard SSD and Premium SSD: expansion beyond **4 TiB** requires
  the volume to be unmounted and detached before updating the PVC. In an authorized
  maintenance window, scale the consuming workload to zero and verify detachment.
- **Premium SSD v2 and Ultra Disk** support online expansion beyond 4 TiB. Do not
  introduce unnecessary workload downtime for this exception.
- Shrinking a volume is not supported. Changing a StorageClass affects future
  provisioning; it does not migrate or resize the existing disk by itself.

For the selected path, increase the existing PVC storage request:

```sh
kubectl patch pvc CLAIM -n NAMESPACE --type merge -p '{"spec":{"resources":{"requests":{"storage":"TARGETGi"}}}}'
```

Restore the original replicas if you had to quiesce the consumer. Wait for rollout
and CSI/filesystem expansion. Verify PVC/PV capacities and use `df` inside the
actual workload mount; an updated request or Azure disk size alone is insufficient.
Check a nonsecret data checksum/sentinel where available. Do not delete/recreate
claims or volumes, edit PV capacity to forge expansion, or change disk SKU as an
unrequested shortcut. Explicitly obtain authorization before an offline path.

Source: https://learn.microsoft.com/en-us/azure/aks/create-volume-azure-disk
