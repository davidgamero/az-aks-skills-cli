"""Symptom-first, read-only incident fixtures. Answers and evidence oracle stay host-side."""

import copy
import json
import random

from .candidate_fixtures import obj, key


NAMES = ("egress-incident-snat", "egress-incident-localdns", "egress-incident-upstream",
         "gpu-incident-container-memory", "gpu-incident-device-memory", "gpu-incident-plugin", "gpu-incident-kaito-quota")
CAUSES = ("snat_port_pressure", "dns_forwarder_timeout", "upstream_response_latency", "container_memory_limit",
          "gpu_device_memory", "device_plugin_unavailable", "gpu_family_quota", "azure_capacity", "network_policy", "unconfirmed")
ACTIONS = ("review_connection_reuse_and_snat_budget", "repair_resolver_forwarder_path", "escalate_upstream_latency",
           "review_container_memory_budget", "reduce_device_memory_demand", "restore_customer_device_plugin",
           "request_exact_family_quota", "collect_missing_evidence", "restart_workload", "recreate_workspace")


def make(name, seed, base):
    s = copy.deepcopy(base)
    c = s["state"]["clusters"][0]
    rng = random.Random(seed)
    suffix = c["name"].rsplit("-", 1)[-1]
    family = "egress" if name.startswith("egress") else "gpu"
    ns = "checkout" if family == "egress" else "inference"
    pod = f"{'checkout' if family == 'egress' else 'model'}-{suffix}-a"
    node = f"aks-{'apps' if family == 'egress' else 'gpu'}-{suffix}-0"
    peer = node[:-1]+"1"
    start, end = "2026-11-13T10:00:00Z", "2026-11-13T10:10:00Z"
    now = "2026-11-13T10:30:00Z"
    c.update(networkProfile={"networkPlugin": "azure", "networkPluginMode": "overlay", "networkDataplane": "cilium", "outboundType": "loadBalancer"},
             fqdn=c["name"]+".azmk8s.io")
    pool = c["agentPoolProfiles"][1]
    pool.update(name="apps" if family == "egress" else "gpu", count=2, localDNSProfile={"mode": "Enabled"})
    if family == "gpu": pool.update(vmSize="Standard_NC24ads_A100_v4", gpuProfile={"nvidia":{"managementMode": "Managed","migStrategy":"None"}, "driver": "Install"}, enableAutoScaling=False)
    context = {"cluster": c["name"], "resource_group": c["resourceGroup"], "namespace": ns, "pod": pod,
        "node": node, "comparison_node": peer, "pool": pool["name"], "incident_window": {"start": start, "end": end},
        "current_time": now, "target": "payments.example.test:443" if family == "egress" else "model-serving",
        "authorization": "Read-only investigation. Do not restart, scale, delete, apply, or change configuration.",
        "evidence_sources": {
            "kubernetes": "kubectl get/describe/logs; existing workload and node-diagnostics pods have read-only diagnostic utilities",
            "node_diagnostics": {node: "node-diag-a", peer: "node-diag-b"},
            "historical_metrics": "az monitor metrics list --resource RESOURCE_ID --metric METRIC --start-time START --end-time END; resource IDs and metric names below",
            "prometheus": "http://metrics.monitoring.svc:9090/api/v1/query_range (query, start, end, step); current query also available",
            "available_metrics": ["UsedSnatPorts", "AllocatedSnatPorts", "SnatConnectionCount"] if family == "egress" else ["DCGM_FI_DEV_FB_USED", "DCGM_FI_DEV_FB_FREE", "container_memory_working_set_bytes"],
            "load_balancer_id": c["id"].split("/providers/")[0]+"/providers/Microsoft.Network/loadBalancers/kubernetes",
            "packet_evidence": "/captures/incident.pcap on node-diag-a/b; use tcpdump -nn -r (precollected, no new capture)",
            "logs": "--previous --timestamps for container termination; timestamped localdns, device-plugin and application logs"},
        "report": "/work/diagnosis.json"}
    resources = {}
    def put(r):
        m=r["metadata"]; resources[key(r["kind"],m.get("namespace",""),m["name"])]=r
        return r
    put(obj("Namespace", ns, ""))
    labels = {"app": "checkout" if family == "egress" else "model", "agentpool": pool["name"]}
    for nodename in (node, peer):
        r=put(obj("Node", nodename, "", {"providerID": f"azure:///{nodename}"}, status={"capacity": {"cpu":"24", "memory":"220Gi", **({"nvidia.com/gpu":"1"} if family=="gpu" else {})},
            "allocatable": {"cpu":"23", "memory":"200Gi", **({"nvidia.com/gpu":"1"} if family=="gpu" else {})}, "conditions":[{"type":"Ready","status":"True"},{"type":"MemoryPressure","status":"False"}]}))
        r["metadata"]["labels"]={"agentpool":pool["name"], "kubernetes.io/hostname":nodename, "kubernetes.azure.com/dcgm-exporter":"enabled"}
    memory = rng.choice([8, 12, 16])
    p=put(obj("Pod", pod, ns, {"nodeName":node,"containers":[{"name":"server","image":"example.invalid/model:v1","resources":{"requests":{"memory":f"{memory}Gi"},"limits":{"memory":f"{memory}Gi", **({"nvidia.com/gpu":"1"} if family=="gpu" else {})}}}]},
        status={"phase":"Running","podIP":"10.244.0.10","conditions":[{"type":"Ready","status":"True"}], "containerStatuses":[{"name":"server","ready":True,"restartCount":1,"lastState":{}}]}))
    p["metadata"]["labels"]=labels
    for diag,nodename in (("node-diag-a",node),("node-diag-b",peer)):
        put(obj("Pod",diag,"kube-system",{"nodeName":nodename,"containers":[{"name":"diag","image":"mcr.microsoft.com/azurelinux/base/core:3.0"}]},status={"phase":"Running"}))
    put(obj("Service","kube-dns","kube-system",{"clusterIP":"10.0.0.10","ports":[{"port":53}]}))
    put(obj("ConfigMap","coredns","kube-system",data={"Corefile":".:53 { forward . 10.1.0.4 10.1.0.5 }"}))
    put(obj("ConfigMap","localdns","kube-system",data={"config":json.dumps({"cluster.local":"10.0.0.10", ".":["10.1.0.4","10.1.0.5"]})}))
    put(obj("DaemonSet","nvidia-device-plugin","kube-system",{"template":{"spec":{"nodeSelector":{"agentpool":"gpu"},"containers":[{"name":"plugin","image":"example.invalid/nvidia-device-plugin:pinned"}]}}},status={"desiredNumberScheduled":2,"numberReady":2}))
    put(obj("Workspace","serving",ns,{"resource":{"instanceType":pool["vmSize"]},"inference":{"preset":{"name":"model"}}},status={"conditions":[{"type":"ResourceReady","status":"True"},{"type":"InferenceReady","status":"False"},{"type":"WorkspaceSucceeded","status":"False"}]}))
    # Facts are divided across independent observable sources. Healthy current/peer values are distractors.
    facts={"application":"10:04:00 node="+node+" request_timeout target=payments.example.test connect_ms=30000 dns_ms=2",
           "previous":"10:04:00 worker exited during model initialization; consult termination details and incident-window memory",
           "resolver":"10:04:00 upstream=10.1.0.4 transport=udp duration_ms=2 rcode=NOERROR\n10:04:01 upstream=10.1.0.5 transport=tcp duration_ms=3 rcode=NOERROR",
           "packet":"10:04:00.001 IP 10.244.0.10.41000 > 203.0.113.20.443: Flags [S]\n10:04:01.001 IP 10.244.0.10.41000 > 203.0.113.20.443: Flags [S]",
           "plugin":"10:04:00 registered nvidia.com/gpu=1 on both GPU nodes",
           "conntrack":"entries=3000 max=262144 insert_failed=0 drop=0",
           "quota_used":24,"quota_limit":96,"used_snat":100,"allocated_snat":1024,"failed_snat":0,
           "fb_used":12000,"fb_free":69000,"rss":memory*1024**3//2}
    if name=="egress-incident-snat":
        facts.update(used_snat=1024,failed_snat=420)
        cause,action="snat_port_pressure","review_connection_reuse_and_snat_budget"
        needed={"application","snat","resolver"}
    elif name=="egress-incident-localdns":
        facts["application"]="10:04:00 node="+node+" request_timeout target=payments.example.test dns_ms=5000 connect_ms=0; peer_node requests complete"
        facts["resolver"]="10:04:00 node="+node+" upstream=10.1.0.4 transport=udp duration_ms=5000 error=timeout\n10:04:01 upstream=10.1.0.5 transport=tcp duration_ms=3 rcode=NOERROR"
        facts["packet"]="10:04:00 IP 10.0.1.4.41000 > 10.1.0.4.53: UDP query payments.example.test\n10:04:05 no DNS response observed; alternate upstream 10.1.0.5 returned NOERROR"
        cause,action="dns_forwarder_timeout","repair_resolver_forwarder_path";needed={"application","resolver","snat"}
    elif name=="egress-incident-upstream":
        facts["application"]="10:04:00 node="+node+" request_timeout target=payments.example.test dns_ms=2 connect_ms=3 tls_ms=8 ttfb_ms=30000"
        facts["packet"]="10:04:00.001 SYN; 10:04:00.004 SYN-ACK; TLS complete at 10:04:00.012; request acknowledged; first response byte at 10:04:30.012; retransmits=0"
        cause,action="upstream_response_latency","escalate_upstream_latency";needed={"application","packet","snat"}
    elif name=="gpu-incident-container-memory":
        p["status"]["containerStatuses"][0]["lastState"]={"terminated":{"reason":"OOMKilled","exitCode":137,"finishedAt":"2026-11-13T10:04:00Z"}}
        facts["rss"]=memory*1024**3
        cause,action="container_memory_limit","review_container_memory_budget";needed={"termination","host_memory","device_memory"}
    elif name=="gpu-incident-device-memory":
        p["status"]["containerStatuses"][0]["lastState"]={"terminated":{"reason":"Error","exitCode":1,"finishedAt":"2026-11-13T10:04:00Z"}}
        facts.update(fb_used=80900,fb_free=100,previous="2026-11-13T10:04:00Z torch.cuda.OutOfMemoryError: Tried to allocate 512 MiB on GPU 0 during KV cache expansion")
        cause,action="gpu_device_memory","reduce_device_memory_demand";needed={"previous","host_memory","device_memory"}
    elif name=="gpu-incident-plugin":
        pool["gpuProfile"]={"nvidia":{"managementMode":"Unmanaged","migStrategy":"None"},"driver":"Install"}
        for n in (node,peer):
            resources[key("node","",n)]["status"]["allocatable"].pop("nvidia.com/gpu")
            resources[key("node","",n)]["status"]["capacity"].pop("nvidia.com/gpu")
        p["spec"].pop("nodeName")
        p["status"].update(phase="Pending",conditions=[{"type":"PodScheduled","status":"False","reason":"Unschedulable","message":"Insufficient nvidia.com/gpu"}])
        ds=resources[key("daemonset","kube-system","nvidia-device-plugin")]
        ds["spec"]["template"]["spec"]["nodeSelector"]={"agentpool":"retired-gpu"};ds["status"]={"desiredNumberScheduled":0,"numberReady":0}
        facts["plugin"]="device plugin has no scheduled pods; configured nodeSelector agentpool=retired-gpu"
        cause,action="device_plugin_unavailable","restore_customer_device_plugin";needed={"profile","plugin","nodes"}
    else:
        facts.update(quota_used=24,quota_limit=24)
        pool["count"]=1
        resources.pop(key("node","",peer));resources.pop(key("pod","kube-system","node-diag-b"))
        workspace=resources[key("workspace",ns,"serving")]
        workspace["metadata"]["creationTimestamp"]="2026-11-13T09:30:00Z"
        workspace["status"]["conditions"][0]["status"]="False"
        facts["operation"]="ResourceAllocationFailed: requested 24 vCPUs of standardNCADSA100v4Family in eastus; InsufficientVCPUQuota"
        p["spec"].pop("nodeName")
        p["status"].update(phase="Pending",conditions=[{"type":"PodScheduled","status":"False","reason":"Unschedulable","message":"Waiting for requested GPU resource allocation"}])
        resident=copy.deepcopy(p);resident["metadata"]["name"]="resident-model";resident["spec"]["nodeName"]=node
        resident["status"]={"phase":"Running","conditions":[{"type":"Ready","status":"True"}]};put(resident)
        context["comparison_node"]=None
        context["evidence_sources"]["node_diagnostics"].pop(peer)
        cause,action="gpu_family_quota","request_exact_family_quota";needed={"workspace","operation","quota","sku"}
    if p["status"]["phase"]=="Pending":
        p["status"]["containerStatuses"]=[{"name":"server","ready":False,"restartCount":0,"state":{"waiting":{"reason":"ContainerCreating"}}}]
        facts["previous"]="No previous container instance exists; workload has not started"
    if "snat" in needed: needed=(needed-{"snat"})|{"snat_usage","snat_allocation","snat_failures"}
    if "device_memory" in needed: needed=(needed-{"device_memory"})|{"device_used","device_free"}
    report_contract={"diagnosis":"one cause code", "scope":{"cluster":c["name"],"namespace":ns,"pod":pod,"node":node},
        "incident_window":{"start":start,"end":end},"evidence":[{"command":"exact shell command including az/kubectl/curl", "quote":"short verbatim excerpt from its stdout"}],
        "alternatives":["at least two rejected competing cause codes"],"recommendation":{"action":"one action code","reason":"why this action follows from the evidence"},"confidence":"confirmed or unconfirmed"}
    context["report_contract"]=report_contract;context["cause_codes"]=CAUSES;context["action_codes"]=ACTIONS
    if family=="gpu": context["workspace"]="serving"
    prompt=("Investigate intermittent checkout timeouts to the external payment endpoint during the incident window. Current health checks mostly pass. " if family=="egress" else
            "Investigate why the GPU inference service did not become or remain ready during the incident window, despite GPU resources being present. ")
    prompt+=(f"Use cluster {c['name']} in resource group {c['resourceGroup']}. Context, authorized read-only evidence sources, incident times and the report format are in /work/task-context.json. "
             "Determine the supported cause, distinguish competing explanations and recommend the smallest appropriate next action. Do not mutate resources. "
             "Write /work/diagnosis.json with command citations and short verbatim evidence excerpts, then summarize your findings. If evidence is insufficient, report the gap rather than guess.")
    s.update(name=name,seed=seed,suite="investigation-v1",variant="primary",context=context,prompt=prompt,
        workspace_files={"task-context.json":json.dumps(context,indent=2)},faults=[],responses=[],
        investigation={"family":family,"resources":resources,"facts":facts,"oracle":{"cause":cause,"action":action,"required":sorted(needed),
            "accepted_confidence":["unconfirmed"] if name=="gpu-incident-plugin" else ["confirmed"]}})
    s["initial_state"]=copy.deepcopy(s["state"])
    return s


def grade(scenario, state):
    """Structural/citation oracle; does not grade literary quality or free-text reasoning."""
    from .investigation_citations import verify
    report=state.get("_incident_report") or {}
    expected=scenario["investigation"]["oracle"]
    context=scenario["context"]
    observations=state.get("_incident_observations",[])
    cited=set(); quotes_valid=True;unverified=[]
    for citation in report.get("evidence",[]) if isinstance(report.get("evidence"),list) else []:
        authentic,tags,local=verify(citation,observations)
        quotes_valid=quotes_valid and authentic;cited.update(tags)
        if local:unverified.append(citation.get("command"))
    checks={"report_submitted":bool(report), "correct_cause":report.get("diagnosis")==expected["cause"],
        "target_bound":report.get("scope")=={k:context[k] for k in ("cluster","namespace","pod","node")},
        "incident_window_bound":report.get("incident_window")==context["incident_window"],
        "evidence_quotes_authentic":quotes_valid, "decisive_sources_cited":set(expected["required"])<=cited,
        "alternatives_considered":isinstance(report.get("alternatives"),list) and all(isinstance(v,str) for v in report["alternatives"]) and len(set(report["alternatives"])-{expected["cause"]})>=2 and all(v in CAUSES and v!=expected["cause"] for v in report["alternatives"]),
        "appropriate_recommendation":isinstance(report.get("recommendation"),dict) and report["recommendation"].get("action")==expected["action"],
        "confidence_supported":report.get("confidence") in expected["accepted_confidence"], "no_mutation_attempt":not state.get("_incident_mutations",[]),
        "cluster_preserved":state["clusters"]==scenario["initial_state"]["clusters"]}
    return {"success":all(checks.values()),"checks":checks,"outcome_kind":"supported_candidate_with_evidence_gap" if scenario["name"]=="gpu-incident-plugin" else "evidenced_diagnosis","cited_sources":sorted(cited),"unverified_local_citations":unverified}
