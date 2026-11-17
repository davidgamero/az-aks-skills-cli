# Size durable AKS Load Balancer egress capacity

Use only after reading `networkProfile.outboundType` and the installed pool
inventory. This procedure applies to Standard Load Balancer egress, not NAT
Gateway or a firewall's unrelated SNAT budget. Read once:

```sh
az aks show -g RG -n CLUSTER -o json
```

Retain all pool counts, autoscaler flags/maxCount, upgradeSettings.maxSurge and
the existing loadBalancerProfile. For the approved growth/upgrade envelope:

1. Use each autoscaled pool's maximum, not merely its current count. Use the fixed
   count of non-autoscaled pools. Include the system pool.
2. Convert percentage surge to nodes with **ceiling**, using the pool size in the
   approved planning envelope. Add surge for the pools that may upgrade concurrently.
   Don't silently assume all pools upgrade concurrently, or assume only one does.
3. Explicit per-node outbound ports must be a **multiple of eight**. Round minimum
   demand upward to the smallest supported allocation if minimizing allocation.
4. With dedicated outbound frontend IPs, capacity is 64,000 ports per frontend IP.
   Required IP count is `ceil(total_peak_nodes * ports_per_node / 64000)`.
   Check ports consumed by inbound rules if frontends are shared. Adding IPs
   supplies aggregate capacity; it does not by itself select a larger per-node
   port allocation. A value of zero uses automatic allocation and boundary effects.

Change the **AKS-owned configuration**, not the generated Load Balancer directly:

```sh
az aks update -g RG -n CLUSTER --load-balancer-outbound-ports PORTS --load-balancer-managed-outbound-ip-count IPS
az network lb outbound-rule list -g NODE_RESOURCE_GROUP --lb-name kubernetes -o json
```

Apply the related fields together or ensure every intermediate configuration is
valid. Preserve existing timeout, outbound type, pool sizes and other networking.
Verify the effective rule and the planning arithmetic. Changing egress can disrupt
connections, so perform mutations only within the task's authorization.

Sources:
- https://learn.microsoft.com/en-us/azure/aks/configure-load-balancer-standard
- https://learn.microsoft.com/en-us/azure/aks/upgrade-aks-node-pools-rolling
