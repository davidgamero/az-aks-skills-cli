# Investigate intermittent AKS egress

Use for an affected pod/destination and an incident window, especially when current
checks pass. Bind the subscription, cluster, node, source pod, target address/port
and times before comparing signals. Investigate read-only unless remediation is
explicitly authorized. Keep at least two plausible competing explanations until
the observations discriminate them.

## Collect decisive evidence in a small number of batches

1. Read the affected pod's timestamped application logs and placement. Separate
   DNS duration, TCP connect, TLS handshake and time to first response byte. A
   generic timeout does not identify which phase stalled.
2. Read `az aks show` networkProfile and `az aks nodepool show` for the actual
   outbound type and LocalDNS configuration. Inspect `/etc/resolv.conf` in the
   affected pod. With LocalDNS, compare node/pool, external/cluster zones and each
   configured forwarder over UDP/TCP; healthy CoreDNS does not establish that the
   node-local external resolver path worked.
3. If Load Balancer supplies egress, read its outbound rule and **incident-window,
   affected-backend** metrics together: UsedSnatPorts, AllocatedSnatPorts and failed
   SnatConnectionCount. Respect available aggregation and dimension names from
   `az monitor metrics list-definitions`. Current low use and cluster averages do
   not refute earlier per-backend exhaustion.

```sh
az monitor metrics list --resource "$LB_ID" --metric UsedSnatPorts,AllocatedSnatPorts,SnatConnectionCount --start-time "$START" --end-time "$END"
```

4. Inspect the selected route and effective NSG/firewall path when relevant. An
   allowed rule alone does not demonstrate packet delivery. Where existing capture
   artifacts are available, compare SYN/SYN-ACK timing, retries, DNS responses and
   response timing. Retrieve/read existing captures with the installed diagnostic
   tools; new privileged capture resources require separate authorization.

## Distinguish the branches

- **SNAT pressure:** incident-time used ports approach allocation on the affected
  backend **and** failed connection telemetry rises. Correlate with connect-phase
  failures, then consider connection reuse and the correctly sized outbound budget.
  A large cluster, a fixed port allocation or retransmits alone are insufficient.
- **Resolver path:** failing requests spend their time resolving; affected-node
  forwarding logs/queries expose the failing forwarder/protocol while another path
  works. Establish the first failing path before changing CoreDNS or LocalDNS.
  LocalDNS configuration changes may reimage nodes.
- **Upstream latency:** DNS, connect and TLS complete quickly, requests reach the
  peer, but response bytes arrive late. With healthy incident-time egress evidence,
  hand off the correlated request window to the dependency owner. Do not prescribe
  SNAT changes simply because the symptom is an external timeout.
- **Missing history:** say which cause remains unconfirmed and what collection is
  needed. A successful current curl is a current observation, not historical proof.

For a report, cite the exact commands and decisive excerpts: affected target/time,
phase timing, per-backend usage/allocation/failures, resolver or packet evidence,
and the alternative each observation weakens. Preserve diagnostic uncertainty;
avoid blanket restarts, DNS changes or switching egress architecture as a test.

Sources (reviewed 2026-11-13; pinned provenance in investigation-sources.json):
- https://github.com/microsoft/skills/tree/main/.github/plugins/aks-skills/skills/aks-troubleshooting
- https://github.com/microsoft/skills/tree/main/.github/plugins/aks-skills/skills/aks-network-capture
- https://learn.microsoft.com/en-us/azure/aks/troubleshoot-source-network-address-translation
- https://learn.microsoft.com/en-us/troubleshoot/azure/azure-kubernetes/connectivity/dns/troubleshoot-localdns
