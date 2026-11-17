# Master AKS skill-comparison scenario list

**58 scenarios: 38 runnable, 20 designed-only.**

This is a research/evaluation registry, not a frequency ranking or a claim that every task needs skills.
New guide-derived cases are documented in [procedure comparison](procedure-comparison.md). Historical evidence is not pooled into the new study.

## Guide-derived procedure candidates

| Scenario | Topic | Status | Specific procedure to test |
|---|---|---|---|
| `procedure-application-consistent-snapshot` | backup | design_only | Quiesce writes using the application's supported protocol, snapshot the correct volume, restore a new consumer and validate application/data consistency rather than snapshot metadata alone. |
| `procedure-autoscaler-scale-down-proof` | autoscaling | design_only | Use requests/allocatable rather than CPU usage alone; inspect move feasibility, PDB/safe-to-evict/local storage and timers; distinguish scale-up cap from scale-down eligibility. |
| `procedure-backup-region-eligibility` | backup | not_live_evaluated | Join PV driver/class and disk size/access/DES fields; separate Operational/Vault tier, paired-region restore and secondary RPO. |
| `procedure-backup-restore-role-chain` | backup | design_only | Separate extension identity, vault identity, trusted access, target/snapshot/staging scopes and restore-tier roles; validate before starting and preserve security constraints. |
| `procedure-cni-dynamic-batches` | network-capacity | design_only | Separate node/pod subnets; account for per-node 16-address allocations, refill below eight free, surge and churn before comparing NNC allocations to apparent demand. |
| `procedure-coredns-import-reload` | dns | not_live_evaluated | Use coredns-custom import suffixes, preserve main/legacy config, reload and verify affected plus preserved query paths. |
| `procedure-csi-retain-migration` | storage | design_only | Set Retain before logical object removal; preserve physical disk handle, prebind replacement CSI PV/PVC and verify data/consumer continuity. |
| `procedure-disk-expand-boundary` | storage | not_live_evaluated | Branch on actual disk SKU, detach when required, grow existing claim, restore consumer and verify mounted filesystem/data without recreation. |
| `procedure-disk-zone-safe-recovery` | storage | design_only | Compare actual disk zone and eligible capacity; preserve truthful topology and data, choose a same-zone pool or approved storage migration instead of falsifying labels/affinity. |
| `procedure-files-key-stale-mount` | storage | design_only | Classify DNS/TCP445 versus SMB auth/cipher failure, verify key version without disclosing it and resolve stale mount/consumer lifecycle through an approved remount path. |
| `procedure-gitops-durable-repair` | gitops | design_only | Trace field ownership to Flux source/path, modify the approved repository overlay, reconcile and verify revision; restore any authorized temporary suspension and avoid prune-driven data loss. |
| `procedure-hpa-sidecar-requests` | autoscaling | design_only | Inspect admitted pod and every container, including injected sidecars, then distinguish resource metric denominator problems from provider/RBAC errors. |
| `procedure-ingress-controller-boundary` | ingress | design_only | Identify actual ingress/Gateway ownership, listener/parent attachment and backend readiness, preserve old routes and verify hostname/TLS/path before authorized DNS cutover. |
| `procedure-kubelet-certificate-scope` | security | design_only | Distinguish serving/client/CA identities, inspect actual expiry/signer/rotation state and choose supported component-specific action; do not approve arbitrary CSRs or rotate the whole cluster blindly. |
| `procedure-local-traffic-health` | ingress | design_only | Join ready local endpoint placement, healthCheckNodePort and Azure probe behavior; distinguish expected nonserving-node probe failure from a real probe/path fault without losing source IP. |
| `procedure-os-retirement-migration` | lifecycle | design_only | Pin retirement dates and supported OS/Kubernetes/FIPS matrix; distinguish node-image refresh from OS SKU migration, stage workload validation and preserve rollback feasibility. |
| `procedure-outbound-migration-cutover` | egress | design_only | Use actual managed/BYO migration matrix, associate required egress resources, update allowlists/authorized IPs and plan disruption/verification before cutover. |
| `procedure-pls-proxy-health` | ingress | design_only | Check PROXY-header support of the actual health endpoint, distinguish kube-proxy health port from app probes and configure an authorized compatible probe/receiver pair. |
| `procedure-priority-expander-match` | autoscaling | design_only | Verify exact group-name regex coverage, priority ordering and fallback eligibility using current pool identities rather than copying ambiguous sample priorities. |
| `procedure-reclaim-released-volume` | storage | design_only | Verify Retain and disk/data identity, resolve the old claim reservation, explicitly bind the new claim and verify content without deleting the physical asset. |
| `procedure-service-ip-expand` | network-capacity | design_only | Gate on supported version/allocator and address plan; add ServiceCIDR, preserve existing IPAddress ownership and verify new allocation; distinguish extension from moving the original service range. |
| `procedure-snat-surge-budget` | egress | not_live_evaluated | Round per-node ports to eight, include all pool maxima and approved concurrent surge, size 64000-port frontends and update the AKS owner rather than its reconciled LB. |
| `procedure-upgrade-subnet-preflight` | upgrade | design_only | Inventory every pool/subnet, distinguish CNI modes, use applicable maxima and surge, account for reserved/other addresses, and select an authorized feasible upgrade envelope. |
| `procedure-webhook-scoped-recovery` | admission | design_only | Read matched webhook rules, service endpoints, TLS and tunnel evidence, then restore the failing relationship or use an explicitly approved narrow exception with rollback. |

## Existing controls and historical scenarios

| Scenario | Topic | Historical report |
|---|---|---|
| `acr-abac-pull-repair` | registry | [candidate-evaluation.md](candidate-evaluation.md) |
| `acr-private-data-endpoint` | registry | [candidate-evaluation.md](candidate-evaluation.md) |
| `api-connectivity-stage-repair` | networking | [candidate-evaluation.md](candidate-evaluation.md) |
| `automatic-admission-mutation-quota` | automatic-nap | [candidate-evaluation.md](candidate-evaluation.md) |
| `automatic-create` | operational-control | [benchmark.md](benchmark.md) |
| `automatic-maintenance` | operational-control | [benchmark.md](benchmark.md) |
| `autoscaler` | operational-control | [benchmark.md](benchmark.md) |
| `control-plane-upgrade` | operational-control | [benchmark.md](benchmark.md) |
| `csi-rotation-consumption-mode` | secrets | [candidate-evaluation.md](candidate-evaluation.md) |
| `csi-secret-sync-alias` | secrets | [candidate-evaluation.md](candidate-evaluation.md) |
| `debug-automatic-provider` | operational-control | [benchmark.md](benchmark.md) |
| `debug-managed-namespace-quota` | operational-control | [benchmark.md](benchmark.md) |
| `debug-version-skew` | operational-control | [benchmark.md](benchmark.md) |
| `egress-incident-localdns` | investigation | [investigation-discovery.md](investigation-discovery.md) |
| `egress-incident-snat` | investigation | [investigation-discovery.md](investigation-discovery.md) |
| `egress-incident-upstream` | investigation | [investigation-discovery.md](investigation-discovery.md) |
| `gateway-api-publish` | ingress | [candidate-evaluation.md](candidate-evaluation.md) |
| `gpu-incident-container-memory` | investigation | [investigation-discovery.md](investigation-discovery.md) |
| `gpu-incident-device-memory` | investigation | [investigation-discovery.md](investigation-discovery.md) |
| `gpu-incident-kaito-quota` | investigation | [investigation-discovery.md](investigation-discovery.md) |
| `gpu-incident-plugin` | investigation | [investigation-discovery.md](investigation-discovery.md) |
| `identity-binding-mixed-audiences` | identity | [candidate-evaluation.md](candidate-evaluation.md) |
| `managed-namespace-adopt-identical` | managed-namespaces | [candidate-evaluation.md](candidate-evaluation.md) |
| `managed-namespace-detach-keep` | managed-namespaces | [candidate-evaluation.md](candidate-evaluation.md) |
| `managed-namespace-rbac-plane` | managed-namespaces | [candidate-evaluation.md](candidate-evaluation.md) |
| `managed-namespace-selective-ingress` | managed-namespaces | [candidate-evaluation.md](candidate-evaluation.md) |
| `manual-scale` | operational-control | [benchmark.md](benchmark.md) |
| `nap-capacity-control-plane` | automatic-nap | [candidate-evaluation.md](candidate-evaluation.md) |
| `nap-image-pickup-versus-disruption` | automatic-nap | [candidate-evaluation.md](candidate-evaluation.md) |
| `overlay-cidr-exhaustion` | networking | [candidate-evaluation.md](candidate-evaluation.md) |
| `pdb-preserving-upgrade` | upgrades | [candidate-evaluation.md](candidate-evaluation.md) |
| `stop-dev` | operational-control | [benchmark.md](benchmark.md) |
| `transient-scale` | operational-control | [benchmark.md](benchmark.md) |
| `workload-federation-versus-rbac` | identity | [candidate-evaluation.md](candidate-evaluation.md) |

The [JSON registry](research/master-scenarios.json) includes source URLs, negative controls, holdout ideas, run revisions and measured deltas when available.
Regenerate with `PYTHONPATH=bench .venv-bench/bin/python bench/master_scenarios.py --runs LIVE_RUN_DIRECTORY`. Do not pass an audit-only directory as a fresh live run.
