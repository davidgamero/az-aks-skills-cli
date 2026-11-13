# Additional task-focused AKS skills and scenario designs

Research reviewed November 13, 2026. These are representative Microsoft-documented
operator workflows, not a frequency-ranked support-ticket survey.

Three new printable recipes are in the standalone `skills/` catalog. They have
not been benchmarked: their ACR, federation and PDB state models are not yet part
of the simulator. The concurrent content-tuning experiment uses frozen versions
of the existing nine-skill benchmark catalog, so these additions do not change
that experiment's inputs.

## Design principles

Each skill aims to reduce the distance from **specific evidence → targeted repair
→ task-level verification**:

- Start from the error and current observations rather than a full AKS inventory.
- Choose the failure branch before making a change; avoid trying every repair.
- Reuse resource IDs and independently available reads in a single tool call.
- Make dependent command sequences complete, while stopping at decision points.
- Verify the actual outcome: image pulled, application can access the resource,
  or upgrade completed without violating availability—not merely a successful PUT.
- Preserve the user's scope and unrelated state. Stopping a broad investigation
  is an optimization only after relevant evidence rules out those branches.

## 1. Restore image pulls from ACR

**Skill:** [`aks-acr-image-pull`](../skills/aks-acr-image-pull/SKILL.md)

Microsoft's [image-pull troubleshooting guide][acr-errors] separates authorization,
login-endpoint connectivity, data-endpoint connectivity, missing images, platform
mismatches, rate limits and stale credential/image caches. Its [AKS/ACR integration
guide][acr-integration] and [triage guide][acr-triage] explicitly distinguish classic
AcrPull from ABAC repository permissions.

### Proposed task

> Restore the API deployment's pulls from the existing registry. Preserve the
> image reference and private-access configuration. You may repair the kubelet's
> pull permission for the approved repository, but not grant push or broad
> administrative access. Verify a new pod pulls the intended image and becomes Ready.

### Variants that require different decisions

| Variant | Seeded fault | Correct branch | Negative control |
|---|---|---|---|
| Classic RBAC | Missing pull assignment on the kubelet identity | Approved AcrPull assignment | Granting it to the control-plane identity |
| ABAC-enabled ACR | Classic AcrPull exists but is ineffective | Repository Reader with the approved condition/scope | Repeating --attach-acr or granting Contributor |
| Data-endpoint failure | Login/manifest path succeeds; layer host is blocked | Repair the specific permitted DNS/egress configuration | Adding more roles or enabling public access |
| Missing image/platform | Wrong tag/digest or incompatible node architecture | Report/correct the authorized image or scheduling choice | Rotating credentials without evidence |

### Required mock state and oracle

Model the registry mode, repository permissions/conditions, kubelet identity,
control-plane identity, image manifest/digest/architecture, login and data endpoint
reachability, and pod pull progress. Support targeted AKS/ACR/role inspection and
the relevant Kubernetes event/read/rollout commands. Scope Azure role-assignment
effects by principal and registry/repository; a generic successful role PUT must
not automatically fix every pull failure.

Pass only when an actual simulated pull of the intended image succeeds and a new
pod is Ready. Preserve image, network restrictions and unrelated permissions.
Include propagation states so the agent cannot mistake temporary latency for a
reason to duplicate assignments. Record diagnostic and mutation calls by branch.

**Optimization hypothesis:** explicit ABAC/identity/endpoint discrimination avoids
wrong-role changes and repeated broad networking or credential investigations.

## 2. Configure or repair passwordless workload access

**Skill:** [`aks-workload-identity`](../skills/aks-workload-identity/SKILL.md)

The [AKS setup guide][wi-setup] defines the service account, identity, federation
and resource-role steps. The [overview][wi-overview] says Automatic preconfigures
OIDC/workload identity and requires the pod-template label. [Entra's federation
contract][federation] requires exact, case-sensitive issuer/subject/audience matches.

### Proposed task

> Enable the payments workload to read the designated Key Vault secret using its
> existing user-assigned identity and service account. Use passwordless federation,
> preserve the image and resource requests, and keep access within the approved
> scope. Verify access from the workload identity rather than from your CLI login.

### Variants

- **Automatic setup:** cluster features are already enabled; the service-account
  annotation, pod label and federated credential are missing.
- **Standard setup:** the same task also requires enabling OIDC/workload identity.
- **Federation repair:** a credential has the wrong namespace in its subject, or
  a mismatched issuer URL; resource authorization is already correct.
- **Authorization repair:** token exchange succeeds but the resource operation is
  denied; changing federation again cannot fix the missing data-plane role.

### Required mock state and oracle

Model clientId versus principalId, cluster issuer, federated credential tuples,
service accounts, Deployment/pod-template mutation, projected token claims,
target-resource role assignments and bounded propagation. A simulated token
exchange must evaluate the tuple; a simulated data-plane probe must separately
evaluate the resulting identity's role and scope.

Pass only after the designated workload obtains access to the intended resource
without introducing a static secret or broader permission. Pod readiness alone
does not prove authorization. Preserve unrelated credentials, identities and
workload settings. A caller CLI session with elevated rights must not satisfy the
workload-access oracle.

**Optimization hypothesis:** reuse identity IDs, skip Automatic's redundant
cluster setup, repair one broken relationship and verify end to end. Separate
propagation from configuration errors rather than recreating credentials repeatedly.

The recipe targets direct federation. Newer identity bindings use a different
audience and need a distinct scenario before mixed-flow behavior can be scored.

## 3. Complete an upgrade while preserving a PDB availability floor

**Skill:** [`aks-pdb-upgrade`](../skills/aks-pdb-upgrade/SKILL.md)

Microsoft's [PodDrainFailure/UpgradeFailed guide][pdb-errors] documents zero
allowed disruptions, adjustments to replicas/budgets, and retrying an upgrade
after repairing the blocker. This case is distinct from the existing version-skew
fixture: it requires a workload availability model during node drain.

### Proposed task

> Resume the failed apps-pool upgrade while keeping at least two API replicas
> available. You may temporarily run a third replica. Keep the PDB and unrelated
> pools unchanged, and restore the original replica count after completion.

The representative initial state is two healthy replicas with absolute
minAvailable=2, so no eviction is permitted. An authorized third healthy replica
creates one allowed disruption without deleting or weakening the PDB.

### Variants and controls

- Spare capacity exists: scale the workload, wait for readiness and a positive
  disruptionsAllowed value, retry the same pool upgrade, then restore replicas.
- The extra replica cannot become Ready: the agent must diagnose capacity or
  admission failure rather than retrying the drain blindly.
- Percentage/zero-unavailability budget: adding one replica may not help. Require
  an authorized budget change or a correct blocked outcome; don't reward bypass.
- An ARM throttling error resembles an eviction error: bounded retry applies to
  the former, not to an unchanged restrictive PDB.

### Required mock state and oracle

Track PDB selectors and policies, desired/healthy replicas, pod placement,
capacity, disruptionsAllowed, drain events, pool upgrade progress and restoration.
The oracle must inspect **the transition history**, not just the final state:
availability must never fall below the required floor, and the budget must never
be deleted or weakened when the task forbids it. Otherwise a destructive shortcut
followed by restoration would incorrectly pass a final-state-only check.

Pass with the requested pool version/Succeeded state, healthy original replica
count, unchanged PDB and unrelated pools, and verified continuity. For an
intentionally unsatisfiable constraint variant, score a supported blocked outcome
separately from successful repair rather than forcing an unsafe mutation.

**Optimization hypothesis:** the error names the blocking PDB, so targeted reads
and a conditional capacity-repair sequence can replace broad cluster scans,
repeated failed upgrade calls and unrelated network/authentication diagnosis.

## Exposing and testing these skills

```sh
./bin/az aks skill show --name aks-acr-image-pull
./bin/az aks skill show --name aks-workload-identity
./bin/az aks skill show --name aks-pdb-upgrade
```

Before adding these tasks to a live agent matrix, implement independent oracles
and meaningful negative controls, replay successful and unsuccessful sequences,
and cover the legitimate diagnostic commands. Keep help-based discovery and
identical prompts across arms. Measure successful repairs, wrong mutations,
skill/doc reads, actual docs requests, modeled service requests and completion
time. Keep held-out error variants separate from scenarios used to edit the skill.

## Catalog map

- `bench/skills/`: nine executable experiment recipes; see the
  [coverage table and tuning experiment](skill-catalog-tuning.md).
- `skills/`: three original examples (upgrade planning, pod diagnostics, pool
  inventory), plus the three new research-derived recipes above.
- The new recipes can be printed by the shim today. Their command sequences and
  service behavior are researched designs, not results from an implemented
  ACR/federation/PDB benchmark.

[acr-errors]: https://learn.microsoft.com/en-us/troubleshoot/azure/azure-kubernetes/connectivity/cannot-pull-image-from-acr-to-aks-cluster
[acr-integration]: https://learn.microsoft.com/en-us/azure/aks/cluster-container-registry-integration
[acr-triage]: https://learn.microsoft.com/en-us/azure/architecture/operator-guides/aks/aks-triage-container-registry
[wi-setup]: https://learn.microsoft.com/en-us/azure/aks/workload-identity-deploy-cluster
[wi-overview]: https://learn.microsoft.com/en-us/azure/aks/workload-identity-overview
[federation]: https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation
[pdb-errors]: https://learn.microsoft.com/en-us/troubleshoot/azure/azure-kubernetes/create-upgrade-delete/error-code-poddrainfailure
