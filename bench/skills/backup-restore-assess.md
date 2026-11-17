# Assess AKS volume eligibility for Vault-tier paired-region restore

Use for an assessment, not an instruction to weaken disk security or initiate a
restore. Read the actual vault configuration, PV source/driver/class and underlying
disk properties. Assess **each volume**, not only the cluster/vault status.

The support matrix reviewed on 2026-11-17 distinguishes:

- Operational snapshots versus offsite Vault tier. Paired-region recovery requires
  eligible **Vault-tier** recovery points, a geo-redundant vault and Cross Region
  Restore enabled; Operational-only snapshots do not establish regional recovery.
- Supported CSI Azure Disk volumes versus in-tree plugins. In-tree volumes are not
  supported. Statically provisioned volumes need an explicit valid storage class
  or can be skipped during backup.
- **Azure Files SMB** can have supported Operational-tier backup, but not Vault-tier
  or cross-region restore. Don't label all CSI drivers as eligible for Vault tier.
- Current vaulted-disk restrictions: disks above the documented 1-TB tiering size
  limit are skipped; restricted disk network access, enabled AAD data-access
  authentication and Disk Encryption Set encryption prevent Vault tiering.
  Inspect public/network access and encryption fields, not just Kubernetes Ready.
  Never recommend relaxing those controls without a separate approved security plan.
- Primary/secondary region and support matrix must fit the actual requested target.
  Vault tier supports paired-region recovery, not arbitrary-region portability.

Join records by PV CSI volumeHandle/disk resource ID. Classify violated fields and
report all blockers. A healthy vault does not make an oversized/private/DES disk
eligible. Treat an absent disk/property or unavailable read as unknown, not eligible.

For recovery-point age, distinguish backup cadence from Vault transfer and regional
replication. The reviewed matrix documents one scheduled Vault recovery point per
day and up to 12 additional replication hours: worst-case secondary-region RPO
**up to 36 hours**, not a four-hour Operational snapshot interval. This is documented
behavior, not a new SLA. Prefer the specific current support matrix over a generic
or older FAQ when the descriptions conflict, and state your source/version.

If planning an actual restore, separately check target extension/trusted access,
staging resources/roles and validation. Those prerequisites do not remove per-volume
eligibility restrictions. Do not enable public access or disable encryption simply
to make an assessment pass.

Sources:
- https://learn.microsoft.com/en-us/azure/backup/azure-kubernetes-service-cluster-backup-support-matrix
- https://learn.microsoft.com/en-us/azure/backup/azure-kubernetes-service-cluster-restore
- https://learn.microsoft.com/en-us/azure/backup/tutorial-restore-aks-backups-across-regions
