# Investigate GPU inference and KAITO readiness

Bind cluster, namespace, workload/container, GPU node/pool and incident time. Read
the actual pod/Workspace conditions and the node pool's gpuProfile before proposing
stack repair. Do not restart, scale, delete Workspaces or reconfigure pools during
a read-only investigation.

## Separate scheduling and initialization

Batch independent reads when targets are known:

```sh
kubectl get pod "$POD" -n "$NS" -o json
kubectl logs "$POD" -n "$NS" -c "$CONTAINER" --previous --timestamps
kubectl get node "$NODE" -o json
az aks nodepool show -g "$RG" --cluster-name "$CLUSTER" -n "$POOL" -o json
```

For Pending workloads, compare selectors, taints/tolerations, requested GPUs,
node capacity/allocatable GPUs and device-plugin component status. Read
`gpuProfile.nvidia.managementMode` together with `gpuProfile.driver`. A GPU VM and
a working NVIDIA driver do not establish that Kubernetes advertises GPU resources.

| Observed profile | Ownership boundary |
|---|---|
| Managed + Install | AKS owns driver, device plugin, exporter and GPU health; collect managed-component/node evidence |
| Unmanaged + Install | AKS installs the driver; inspect the customer's device-plugin deployment/DaemonSet |
| Unmanaged + None | Inspect customer driver and device-plugin owners |
| Missing/contradictory | Keep ownership unconfirmed |

Compare a plugin DaemonSet's nodeSelector to actual node labels and scheduled/Ready
counts. Do not install a second device plugin over the managed stack. Profile fields
are creation-time choices; a profile change is a new-pool plan, not an in-place fix.

## Distinguish container memory from GPU memory

- `OOMKilled` plus container memory at its limit supports a container-memory path.
  Exit 137 alone is insufficient. Check node MemoryPressure as a competing cause.
- A CUDA allocation exception requires **per-GPU, affected-pod, incident-window**
  DCGM evidence: FB_USED and FB_FREE. Healthy idle GPUs or current `nvidia-smi`
  snapshots do not refute a prior peak.
- Correlate historical `container_memory_working_set_bytes` with the container
  limit even when investigating GPU OOM. Host/container and device memory are
  distinct budgets; increasing one does not automatically repair the other.
- Managed+Install pools expose the managed exporter on port 19400; discover the
  actual port for customer-managed exporters. Current exporter metrics are not a
  historical time series. Use the existing telemetry backend's range queries when
  available; do not enable monitoring as an unrequested mutation.

Example Prometheus range API: `/api/v1/query_range?query=METRIC{pod="POD"}&start=START&end=END&step=60`.
Read `DCGM_FI_DEV_FB_USED`, `DCGM_FI_DEV_FB_FREE` and container memory separately;
preserve pod/node/GPU labels and timestamps in citations.

## KAITO provisioning branch

Read Workspace ResourceReady, InferenceReady and WorkspaceSucceeded conditions
when present, creation time, region and requested instance type. Read the failed
Azure allocation operation, then compare the **exact VM family's** current usage,
limit and requested increment. Plenty of regional total-vCPU quota does not imply
family quota is available. Query SKU restrictions separately: quota exhaustion,
SKU eligibility and transient regional capacity are different conclusions.

Machine/Workspace readiness can take time; use the documented window and observed
status before declaring a fault. Workspace deletion leaves provisioned GPU pools;
it is not a quota recovery strategy. Preserve evidence and recommend an exact
family quota request or supported owner action only when the facts justify it.

Report target/time, supporting command excerpts, two considered alternatives,
confidence and the smallest appropriate next action. Do not use model-size tables
or hardware presence alone as proof of the incident cause.

Sources:
- https://github.com/microsoft/skills/tree/main/.github/plugins/aks-skills/skills/aks-gpu-inference
- https://learn.microsoft.com/en-us/azure/aks/aks-managed-gpu-nodes
- https://learn.microsoft.com/en-us/azure/aks/best-practices-gpu-observability
- https://learn.microsoft.com/en-us/azure/aks/ai-toolchain-operator
