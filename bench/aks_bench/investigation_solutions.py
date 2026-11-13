"""Host-only evidence reference; never installed in agent containers."""

import shlex

from .investigations import CAUSES


def commands(s):
    x=s["context"];c=s["state"]["clusters"][0]
    def kube(*args): return {"tool":"kubectl","argv":list(args)}
    result=[kube("get","pod",x["pod"],"-n",x["namespace"],"-o","json"),kube("get","nodes","-o","json"),
        ["aks","nodepool","show","-g",x["resource_group"],"--cluster-name",x["cluster"],"-n",x["pool"]]]
    if s["investigation"]["family"]=="egress":
        result += [kube("logs",x["pod"],"-n",x["namespace"],"--timestamps"),
            kube("exec","node-diag-a","-n","kube-system","--","journalctl","-u","localdns"),
            kube("exec","node-diag-a","-n","kube-system","--","tcpdump","-nn","-r","/captures/incident.pcap"),
            ["monitor","metrics","list","--resource",x["evidence_sources"]["load_balancer_id"],"--metric","UsedSnatPorts,AllocatedSnatPorts,SnatConnectionCount",
             "--start-time",x["incident_window"]["start"],"--end-time",x["incident_window"]["end"]]]
    else:
        if s["name"] not in ("gpu-incident-plugin","gpu-incident-kaito-quota"):
            result.append(kube("logs",x["pod"],"-n",x["namespace"],"--previous","--timestamps"))
        result += [kube("get","daemonset","nvidia-device-plugin","-n","kube-system","-o","json"),
            kube("get","workspace","serving","-n",x["namespace"],"-o","json"),
            ["monitor","activity-log","list","--resource-id",c["id"]], ["vm","list-usage","--location","eastus"],
            ["vm","list-skus","--location","eastus","--all"]]
        for metric in ("DCGM_FI_DEV_FB_USED","DCGM_FI_DEV_FB_FREE","container_memory_working_set_bytes"):
            result.append({"tool":"curl","argv":["-G","--data-urlencode",f'query={metric}{{pod="{x["pod"]}"}}',
                "--data-urlencode","start="+x["incident_window"]["start"],"--data-urlencode","end="+x["incident_window"]["end"],
                "--data-urlencode","step=60","http://metrics.monitoring.svc:9090/api/v1/query_range"]})
    return result+[{"reference_incident_report":True}]


def report(s,state):
    oracle=s["investigation"]["oracle"];x=s["context"]
    return {"diagnosis":oracle["cause"],"scope":{k:x[k] for k in ("cluster","namespace","pod","node")},
        "incident_window":x["incident_window"],"evidence":[{"command":shlex.join([e["tool"],*e["argv"]]),"quote":e["stdout"].strip()} for e in state.get("_incident_observations",[])],
        "alternatives":[v for v in CAUSES if v!=oracle["cause"]][:2],"recommendation":{"action":oracle["action"],"reason":"Supported by correlated incident evidence."},"confidence":oracle["accepted_confidence"][0]}
