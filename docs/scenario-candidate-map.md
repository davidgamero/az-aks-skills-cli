# FAQ/guide → topic → task → benchmark candidate map

## Deliverables

- **24 source snapshots:** 23 Microsoft Learn pages and one upstream Kubernetes
  reference. Full responses, hashes, fetch timestamps and available source revision
  metadata are local at `benchmark-results/research-library-20261113/manifest.json`.
- [Source index](research/aks-source-index.json): URLs, topics, reviewed sections
  and why each source matters.
- [17 structured candidates](research/scenario-candidates.json): natural task
  prompts, decision boundaries, skill outlines, discovery surfaces, mock-state
  requirements, independent oracles, negative controls and held-out variants.
- [Observed task/action map](task-action-skill-map.md): what has actually led to
  skill reads in the existing experiments.

All 17 now have bounded primary fixtures, bringing the runnable matrix to 27 tasks.
The held-out variants below remain research designs. See
[candidate evaluation](candidate-evaluation.md) for implementation limits and live
evidence. Priorities are hypotheses, not production frequency or measured efficacy.

## Why these candidates are stronger tests

The existing no-skills Sol agent usually solved familiar tasks without searching.
More simple scale/create examples will not establish saved searches when the
baseline performs none. Better candidates have a decisive product rule, multiple
plausible failure branches, or an end-to-end dependency across resource types.

The goal is to test whether a compact procedure prevents **wrong branches,
repeated searches or avoidable calls** while preserving correctness—not to hide
an answer in a skill or cripple the baseline. All decisive facts must remain
available through ordinary state inspection and the same public documentation.

## Topic and task map

P1: proposed first implementation/evaluation wave. P2: follow-up or additional
contract validation required. Detailed prompts and assertions are in the JSON.

| Topic | Candidate task | Priority | Decisive knowledge | Potential avoided work |
|---|---|---|---|---|
| Managed namespaces | Adopt existing namespace without changing it | P1 | IfIdentical versus Always/Never; reconcile observed fields | Failed adoption loops or forced overwrites |
| Managed namespaces | Remove ARM management, keep workloads/data | P1 | Keep versus Delete; ARM resource versus Kubernetes namespace | Wrong delete path and recreation |
| Managed namespaces | Fix ARM-visible but Kubernetes-forbidden access | P2 | Management-plane roles differ from data-plane roles | Repeated kubeconfig downloads or excessive grants |
| Managed namespaces | Permit one cross-namespace ingress source | P2, validation gate | Ownership and additive effective policy | Allow-all fixes that break isolation |
| Registry | Repair pulls after ABAC-mode migration | P1 | Kubelet principal; Repository Reader versus AcrPull | Ineffective attach-acr/role changes |
| Registry | Repair blob downloads after login succeeds | P2 | Login and data endpoints are separate | Credential work that cannot fix data-path failure |
| Identity | Repair federation versus resource authorization | P2 | Token tuple and target RBAC are different layers | Rebuilding the whole identity chain |
| Identity | Mix identity binding and direct federation | P2, version gate | Separate audiences/token files, SDK opt-in and binding RBAC | Recreating credentials or breaking the working flow |
| Automatic/NAP | Restore capacity through the correct pool API | P1 | ARM pool versus Karpenter CRD; dynamic versus static limits | Wrong-plane scaling and quota requests |
| Automatic/NAP | Diagnose image pickup versus node replacement | P2 | Maintenance window versus drift/disruption budgets | Repeated schedule/channel changes |
| Automatic/NAP | Fit an admitted workload into fixed quota | P1 | Safeguard mutation can change effective resources | Raising the wrong limit or disabling enforcement |
| Upgrades | Resume PDB-blocked upgrade preserving availability | P2 | Positive disruption allowance and temporal invariants | Blind retries, forced drain or budget deletion |
| Secrets | Repair CSI secret sync/mounted alias mapping | P1 | A consumer mount is required; aliases must match | IAM changes when synchronization is the problem |
| Secrets | Make an app observe a rotated secret | P2 | Source/mount/Secret/app layers; env versus volume | Polling or reinstalling an already-working layer |
| Networking | Expand exhausted Overlay pod CIDR | P2 | Eligible contiguous superset; NNC reconciliation | Wrong quota changes or cluster recreation |
| Networking | Restore logs/exec when API reads work | P2 | Client path, authz and kubelet/tunnel path differ | Fixing credentials or API exposure unnecessarily |
| Ingress | Publish through managed Gateway API | P2, version gate | approuting-istio, managed CRDs, mode/version defaults | Wrong controller/class and redundant enablement |

## Recommended first implementation batch

### 1. Managed namespace adoption and detachment

These reuse the managed-namespace state already present in the mock, but add
creation/adoption/deletion semantics. They have clear user-visible outcomes and
natural `az aks namespace ... --help` entry points. The skill can be a short,
complete procedure rather than an encyclopedia.

- Adoption must preserve semantic quota/policy values and namespace/workload UIDs.
- Detachment must remove only ARM management and preserve namespace, app and data
  identity. A delete/recreate shortcut must fail even if names match afterward.
- Validate managed child-resource cleanup before asserting details not promised
  by the guide.

Sources: [managed-namespace concepts][ns-concepts] and [usage guide][ns-guide].

### 2. ABAC-specific ACR pull repair

There is already a draft `aks-acr-image-pull` skill. A registry can have an AcrPull
assignment and still reject pulls in ABAC mode. The correct identity is the
kubelet principal, and repository-limited access needs an appropriate condition.
Repository Reader does not imply catalog-listing permission: failure to list
every repository is not proof that the approved image pull is broken.

Score a fresh pull as the kubelet plus positive/negative repository probes.
Don't score only successful role-assignment creation. Include a classic-RBAC
held-out case so the skill cannot win by always choosing an ABAC role.

Sources: [ACR integration][acr-integration], [ABAC roles/conditions][acr-abac],
and [image-pull troubleshooting][acr-errors].

### 3. CSI secret synchronization

The sync object may be absent despite successful Key Vault access because no
pod mounts the SecretProviderClass, or secretObjects refers to the wrong mounted
alias. That distinction can prevent repeated permission changes.

Model the consumer lifecycle and actual sync result. Verify the app consumes the
intended version using nonsecret metadata/sentinels. Keep identity permissions
unchanged in the synchronization-fault variant.

Sources: [CSI configuration][csi-config] and [CSI troubleshooting][csi-tsg].

### 4. Automatic admission mutation and NAP capacity ownership

These extend beyond the current quota fixture. The submitted workload may be
mutated before quota evaluation, and pending capacity may be governed by a
Karpenter NodePool rather than an ARM agent pool. They are promising but need
more state modeling than the lifecycle cases.

- Compare submitted and admitted resources; pin the actual safeguard version.
- Distinguish dynamic NAP resource ceilings from static replicas/limits.nodes.
- Keep Azure quota, pod scheduling constraints and NodeClass/NodeClaim health as
  separate variables so one generic scale command cannot fix every variant.

Sources: [Deployment Safeguards and FAQ][safeguards], [NAP pool guide][nap-pools],
and [NAP troubleshooting][nap-tsg].

## Important source/version gates

1. **Identity bindings are not universally available.** The current concepts and
   setup guides exclude API-server VNet integration and require specific SDK
   support/opt-in. Automatic's workload-identity default does not establish
   identity-binding support. Use a supported cluster for the success case and a
   justified blocked outcome for the incompatible configuration.
2. **NAP image windows are not a blanket disruption guarantee.** The guide says
   the AKS window controls image pickup; drift logic and node/pod budgets govern
   replacement. Model the clock and both policy layers separately.
3. **NetworkPolicy wording needs a contract check.** The managed-namespace guide
   suggests AllowAll followed by a custom restriction, while standard Kubernetes
   policies combine their allowed traffic additively. Inspect generated resource
   kinds and test effective traffic before making that a gold repair. A narrower
   standard allow cannot override an existing allow-all.
4. **Automatic admission uses both mutation and rejection.** Start with clearly
   documented cases. Verify ambiguous partial-resource mutation behavior against
   the policy definition rather than treating prose as executable truth.
5. **Gateway defaults are version/configuration dependent.** New Automatic 1.36+
   behavior is not a statement that every existing cluster already has it. Keep
   app routing and the separate Istio mesh implementation distinct.
6. **FAQ answers are a topic index, not timeless rules.** Some entries contain
   historical workarounds, old CLI-extension references or date-sensitive support
   policies. Use the focused guide and an explicit as-of feature contract for
   benchmark oracles. Don't copy a workaround such as running a workload as root
   into an optimization recipe without checking the current supported mechanism.

Sources: [binding concepts][ib-concepts], [binding setup][ib-setup],
[workload identity overview][wi-overview], [NAP image updates][nap-images],
[upstream NetworkPolicy semantics][netpol], [Gateway API guide][gateway],
and [AKS FAQ][faq].

## How to establish real value

### Baseline prescreen

Run the no-skills agent on several seeded variants with functioning docs access.
Keep candidates where the baseline repeatedly chooses a wrong branch, makes
avoidable mutations, or performs material documentation/search work. If it
already solves a case with minimal work and no searches, retain it as a control
rather than claiming a large opportunity for search savings.

### Discovery gate

Record the action that exposes the skill entry, the completed help output, and
the first lookup/read. The observed successful route so far is failed Automatic
creation → create help → skill help/list/search → show. That does not prove that
kubectl-heavy CSI or network cases will encounter an AKS-only help overlay.

Each JSON candidate lists likely help surfaces and gaps. Do not silently add
prompt hints to compensate. Test generic versus task-specific help links as a
separate intervention if needed. A body revision cannot help an agent that never
reads the body.

### Correctness gate

The oracle must cover the real desired outcome and preserved constraints:
effective authorization, both allowed/denied traffic paths, actual workload
readiness, application-visible secret version, and temporal availability where
needed. Distinguish successful repair from a correctly evidenced unsupported or
blocked outcome. Never use a skill read itself as a task-success requirement.

### Efficiency gate

Use the same model/provider, prompts, state, source versions and service delays
across conditions. Freeze original/revised skill catalogs and interleave paired
trials. Measure verified completion, wrong mutations, model calls, documentation
lookups, and modeled service requests separately. Source snapshots are a
reproducibility input, not a way to give only the skills arm unavailable facts.

Both arms need access to the relevant sources. For the policy-semantic candidate,
the upstream Kubernetes reference needs an approved read-only path or a shared
snapshot; the current isolated browsing configuration is Learn-focused. Validate
native fetch, curl and ordinary diagnostic coverage before performance trials.

Use development cases for writing the skill and different held-out error variants
for evaluation. Earlier simulator-gap and transport-failure lessons remain
applicable: those are harness failures, not evidence that the baseline model is
bad. No new candidate efficacy runs were performed during this research pass.

## FAQ-derived controls to keep, but not prioritize for speed claims

The FAQ supplies useful negative controls: moving/renaming an AKS cluster,
scaling system pools to zero, changing node capacity through VMSS APIs, and
editing managed node-resource-group internals. These test scope and supported
actions. Most are single-fact questions that a strong model may answer directly;
they are weaker candidates for demonstrating skill retrieval paying for itself.

[faq]: https://learn.microsoft.com/en-us/azure/aks/faq
[ns-concepts]: https://learn.microsoft.com/en-us/azure/aks/concepts-managed-namespaces
[ns-guide]: https://learn.microsoft.com/en-us/azure/aks/managed-namespaces
[acr-integration]: https://learn.microsoft.com/en-us/azure/aks/cluster-container-registry-integration
[acr-abac]: https://learn.microsoft.com/en-us/azure/container-registry/container-registry-rbac-abac-repository-permissions
[acr-errors]: https://learn.microsoft.com/en-us/troubleshoot/azure/azure-kubernetes/connectivity/cannot-pull-image-from-acr-to-aks-cluster
[csi-config]: https://learn.microsoft.com/en-us/azure/aks/csi-secrets-store-configuration-options
[csi-tsg]: https://learn.microsoft.com/en-us/troubleshoot/azure/azure-kubernetes/extensions/troubleshoot-key-vault-csi-secrets-store-csi-driver
[safeguards]: https://learn.microsoft.com/en-us/azure/aks/deployment-safeguards
[nap-pools]: https://learn.microsoft.com/en-us/azure/aks/node-auto-provisioning-node-pools
[nap-tsg]: https://learn.microsoft.com/en-us/troubleshoot/azure/azure-kubernetes/extensions/troubleshoot-node-auto-provision
[nap-images]: https://learn.microsoft.com/en-us/azure/aks/node-auto-provisioning-upgrade-image
[ib-concepts]: https://learn.microsoft.com/en-us/azure/aks/identity-bindings-concepts
[ib-setup]: https://learn.microsoft.com/en-us/azure/aks/identity-bindings
[wi-overview]: https://learn.microsoft.com/en-us/azure/aks/workload-identity-overview
[gateway]: https://learn.microsoft.com/en-us/azure/aks/app-routing-gateway-api
[netpol]: https://kubernetes.io/docs/concepts/services-networking/network-policies/
