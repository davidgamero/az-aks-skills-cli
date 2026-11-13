"""Bounded incident evidence tools; no host command execution or live resource access."""

import copy
import json
import shlex
from urllib.parse import parse_qs, urlparse

from .candidate_runtime import World, WorldError, canonical, parse, BOOLS

BOOLS.update({"--previous", "--timestamps", "--all-containers", "--prefix", "--show-kind"})


class Evidence:
    def __init__(self, scenario):
        self.s=scenario;self.x=scenario["context"];self.c=scenario["state"]["clusters"][0]
        self.f=scenario["investigation"]["facts"];self.resources=scenario["investigation"]["resources"]
        self.family=scenario["investigation"]["family"]

    def window(self, options):
        start=options.get("--start-time",options.get("start"));end=options.get("--end-time",options.get("end"))
        if not start or not end: return False
        def epoch(value):
            from datetime import datetime
            try: return float(value)
            except ValueError: return datetime.fromisoformat(value.replace("Z","+00:00")).timestamp()
        try: return epoch(start)<=epoch("2026-11-13T10:04:00Z")<=epoch(end)
        except (ValueError,TypeError): return False

    def invoke(self, tool, argv):
        if tool=="curl": value,signals=self.curl(argv);options={}
        else:
            words,options,tail=parse(argv,tool)
            if tool=="az": value,signals=self.az(words,options)
            elif tool=="kubectl": value,signals=self.kube(words,options,tail)
            else: raise WorldError("MockNotImplemented","tool outside incident model",0,2)
        return World.encode(self,value,options),signals

    def az(self, words, o):
        command=" ".join(words)
        if command=="account show": return {"id":"00000000-0000-0000-0000-000000000001","name":"Incident sandbox"},{}
        if command=="version": return {"azure-cli":"2.86.0"},{}
        if command in ("aks show","aks list"):
            if o.get("--name",self.c["name"])!=self.c["name"]: raise WorldError("ResourceNotFound","cluster not found",404)
            return (self.c if command.endswith("show") else [self.c]),{"profile":["Unmanaged","Managed","localDNSProfile","loadBalancer"]}
        if command in ("aks nodepool show","aks nodepool list"):
            pools=self.c["agentPoolProfiles"]
            value=pools if command.endswith("list") else next((p for p in pools if p["name"]==o.get("--name")),None)
            if value is None: raise WorldError("ResourceNotFound","pool not found",404)
            return value,{"profile":["Unmanaged","Managed","localDNSProfile"]}
        if command=="monitor metrics list-definitions":
            return [{"name":{"value":n},"primaryAggregationType":"Maximum","dimensions":[{"value":"BackendIPAddress"}]} for n in self.x["evidence_sources"]["available_metrics"]],{}
        if command=="monitor metrics list":
            if o.get("--resource")!=self.x["evidence_sources"]["load_balancer_id"]: raise WorldError("ResourceNotFound","metric resource not found",404)
            metric=o.get("--metric",o.get("--metrics",""))
            requested=metric.replace(","," ").split()
            if not requested: raise WorldError("ArgumentError","--metric required",0,2)
            rows=[];signal={};historical=self.window(o)
            for name in requested:
                if name not in ("UsedSnatPorts","AllocatedSnatPorts","SnatConnectionCount"): raise WorldError("MockNotImplemented","metric outside fixture",0,2)
                value={"UsedSnatPorts":self.f["used_snat"] if historical else 60,"AllocatedSnatPorts":self.f["allocated_snat"],"SnatConnectionCount":self.f["failed_snat"] if historical else 0}[name]
                rows.append({"name":{"value":name},"timeseries":[{"metadatavalues":[{"name":{"value":"Node"},"value":self.x["node"]},*([{"name":{"value":"ConnectionState"},"value":"Failed"}] if name=="SnatConnectionCount" else [])],
                    "data":[{"timeStamp":"2026-11-13T10:04:00Z" if historical else self.x["current_time"],"maximum":value,"total":value}]}]})
                signal[{"UsedSnatPorts":"snat_usage","AllocatedSnatPorts":"snat_allocation","SnatConnectionCount":"snat_failures"}[name]]=[f'"maximum": {value}',f'"total": {value}']
            return {"value":rows},signal if historical else {}
        if command in ("network lb show","network lb outbound-rule list"):
            value={"id":self.x["evidence_sources"]["load_balancer_id"],"name":"kubernetes","outboundRules":[{"name":"aksOutboundRule","allocatedOutboundPorts":1024,"protocol":"All","idleTimeoutInMinutes":4}]}
            return value,{}
        if command in ("network nic list-effective-nsg","network nsg show","network nsg rule list"):
            return {"rules":[{"name":"allow-required","access":"Allow","destinationAddressPrefix":"*","destinationPortRange":"443","direction":"Outbound"}],"defaultDenyAppliesToTarget":False},{}
        if command in ("network nic show-effective-route-table","network route-table show"):
            return {"routes":[{"addressPrefix":"0.0.0.0/0","nextHopType":"Internet","state":"Active"}]},{}
        if command=="vm list-usage":
            return [{"name":{"value":"standardNCADSA100v4Family"},"currentValue":self.f["quota_used"],"limit":self.f["quota_limit"]},
                    {"name":{"value":"cores"},"currentValue":80,"limit":1000}],{"quota":["standardNCADSA100v4Family"]}
        if command=="vm list-skus":
            return [{"name":"Standard_NC24ads_A100_v4","family":"standardNCADSA100v4Family","locations":["eastus"],"restrictions":[],"capabilities":[{"name":"vCPUs","value":"24"}]}],{"sku":["restrictions","vCPUs"]}
        if command in ("monitor activity-log list","aks operation show-latest"):
            return [{"eventTimestamp":"2026-11-13T10:04:00Z","resourceId":self.c["id"],"status":{"value":"Failed" if "operation" in self.f else "Succeeded"},
                     "properties":{"statusMessage":self.f.get("operation","No failed ARM allocation operations in incident window")}}],{"operation":["InsufficientVCPUQuota"]}
        if command=="aks get-credentials": return "Context already configured for "+self.c["name"],{}
        if command=="monitor log-analytics query":
            query=o.get("--analytics-query","")
            if "localdns" in query.lower(): return self.f["resolver"],{"resolver":["duration_ms="]}
            raise WorldError("MockNotImplemented","Kusto query outside incident fixture; use advertised metrics and logs",0,2)
        raise WorldError("MockNotImplemented",command,0,2)

    def kube(self, words,o,tail):
        if not words: raise WorldError("ArgumentError","kubectl command required",0,2)
        action=words[0];ns=o.get("--namespace",self.x["namespace"])
        if action=="config": return self.c["name"] if words[-1]=="current-context" else {"current-context":self.c["name"]},{}
        if action in ("api-resources","version"): return {"resources":sorted({r["kind"] for r in self.resources.values()})},{}
        if action=="auth": return "yes",{}
        if action=="top": return {"pod":self.x["pod"],"memory":"1024Mi","cpu":"100m","time":self.x["current_time"]},{}
        if action=="logs":
            ref=" ".join(words[1:])+" "+str(o.get("--selector",""))
            if "localdns" in ref or "coredns" in ref:
                return ("10:04:00 queries succeeded on healthy comparison node" if "node-diag-b" in ref else self.f["resolver"]),{"resolver":["duration_ms="]}
            if "plugin" in ref: return self.f["plugin"],{"plugin":["retired-gpu","registered"]}
            if "operator" in ref or "kaito" in ref: return self.f.get("operation","Reconciliation completed; inspect Workspace conditions"),{"operation":["InsufficientVCPUQuota"]}
            if self.x["pod"] not in ref and not ref.startswith("deployment/"): raise WorldError("NotFound","log target not found",404)
            if self.family=="egress": return self.f["application"],{"application":["dns_ms=","ttfb_ms="]}
            return (self.f["previous"] if o.get("--previous") else "2026-11-13T10:30:00Z server process currently running"),{"previous":["torch.cuda.OutOfMemoryError","initialization"]} if o.get("--previous") else {}
        if action=="exec":
            if len(words)<2: raise WorldError("ArgumentError","exec target required",0,2)
            name=words[1].split("/")[-1]
            if not any(r["kind"]=="Pod" and r["metadata"]["name"]==name and r["metadata"].get("namespace")==ns for r in self.resources.values()): raise WorldError("NotFound","exec target not found",404)
            if tail[:2] in (["sh","-c"],["bash","-c"]) and len(tail)==3:
                if any(c in tail[2] for c in (";","|","&&","$(","`")): raise WorldError("MockNotImplemented","compound remote shell outside fixture",0,2)
                tail=shlex.split(tail[2])
            text=" ".join(tail)
            if text=="cat /etc/resolv.conf": return "nameserver 169.254.10.10\nsearch "+ns+".svc.cluster.local svc.cluster.local\noptions ndots:5",{}
            if tail and tail[0] in ("dig","nslookup"):
                failed="@10.1.0.4" in tail and self.s["name"]=="egress-incident-localdns" and name!="node-diag-b" and "+tcp" not in tail
                return (";; connection timed out; no servers could be reached" if failed else "payments.example.test. 30 IN A 203.0.113.20\n;; Query time: 2 msec"),{}
            if tail and tail[0]=="tcpdump" and "-r" in tail and tail[tail.index("-r")+1]=="/captures/incident.pcap":
                return (self.f["packet"] if name!="node-diag-b" else "10:04:00 SYN, SYN-ACK; TLS complete; HTTP response in 20ms"),{"packet":["first response byte","Flags [S]","no DNS response"]} if name!="node-diag-b" else {}
            if tail and tail[0]=="journalctl" and "localdns" in text: return self.f["resolver"],{"resolver":["duration_ms="]}
            if tail and tail[0]=="conntrack": return self.f["conntrack"],{}
            if tail and tail[0]=="ss": return "ESTAB 0 0 10.244.0.10:41000 203.0.113.20:443",{}
            if tail and tail[0]=="nvidia-smi": return "GPU 0 NVIDIA A100; Driver 550.54; memory.used 2000 MiB; memory.total 81000 MiB; current snapshot "+self.x["current_time"],{}
            if tail and tail[0]=="curl": return self.curl(tail[1:])
            raise WorldError("MockNotImplemented","remote diagnostic outside fixture: "+text,0,2)
        if action not in ("get","describe"): raise WorldError("MockNotImplemented","kubectl "+action,0,2)
        if o.get("--raw"): return {"gitVersion":"v1.34.2"},{}
        if len(words)<2: raise WorldError("ArgumentError","resource type required",0,2)
        kindname=words[1].split("/",1); kinds=[canonical(k) for k in kindname[0].split(",")]
        kinds=[{"workspaces":"workspace","ds":"daemonset","daemonsets":"daemonset","endpointslices":"endpointslice"}.get(k,k) for k in kinds]
        name=kindname[1] if len(kindname)>1 else words[2] if len(words)>2 else None
        if "event" in kinds:
            return {"items":[{"lastTimestamp":"2026-11-13T10:04:00Z","reason":"Warning","message":"Intermittent request failure" if self.family=="egress" else "Inference readiness unavailable; inspect affected resource and historical telemetry"}]},{}
        selected=[];signals={}
        for r in self.resources.values():
            if canonical(r["kind"]) not in kinds or name and r["metadata"]["name"]!=name: continue
            if r["metadata"].get("namespace") and r["metadata"]["namespace"]!=ns and not (o.get("-A") or o.get("--all-namespaces")): continue
            if o.get("--selector"):
                selectors=o["--selector"].split(",")
                if any("=" in item and r["metadata"].get("labels",{}).get(item.split("=",1)[0])!=item.split("=",1)[1] for item in selectors): continue
            selected.append(copy.deepcopy(r))
            if r["kind"]=="Pod" and r["metadata"]["name"]==self.x["pod"]: signals["termination"]=["OOMKilled","exitCode","Insufficient nvidia.com/gpu"]
            if r["kind"]=="Node": signals["nodes"]=["allocatable","nvidia.com/gpu","MemoryPressure"]
            if r["kind"]=="DaemonSet": signals["plugin"]=["retired-gpu","numberReady"]
            if r["kind"]=="Workspace": signals["workspace"]=["ResourceReady","InferenceReady","instanceType"]
        if name and not selected: raise WorldError("NotFound","resource not found",404)
        return (selected[0] if name else {"apiVersion":"v1","kind":"List","items":selected}),signals

    def curl(self, argv):
        urls=[a for a in argv if a.startswith(("http://","https://"))]
        if not urls: raise WorldError("ArgumentError","URL required",0,2)
        url=urlparse(urls[-1]);params={k:v[-1] for k,v in parse_qs(url.query).items()}
        for i,arg in enumerate(argv):
            if arg in ("--data-urlencode","--data","-d") and i+1<len(argv):
                k,_,v=argv[i+1].partition("=");params[k]=v
        if url.hostname=="metrics.monitoring.svc":
            query=params.get("query","");historical=url.path.endswith("query_range") and self.window(params)
            metric=next((m for m in ("DCGM_FI_DEV_FB_USED","DCGM_FI_DEV_FB_FREE","DCGM_FI_DEV_GPU_UTIL","container_memory_working_set_bytes") if m in query),None)
            if metric is None: raise WorldError("MockNotImplemented","PromQL metric outside fixture",0,2)
            val={"DCGM_FI_DEV_FB_USED":self.f["fb_used"],"DCGM_FI_DEV_FB_FREE":self.f["fb_free"],"DCGM_FI_DEV_GPU_UTIL":0,"container_memory_working_set_bytes":self.f["rss"]}[metric] if historical else 1024
            labels={"__name__":metric,"namespace":self.x["namespace"],"pod":self.x["pod"],"node":self.x["node"],"container":"server","gpu":"0"}
            result=[{"metric":labels,"values":[[1794564240,str(val)]]},{"metric":{**labels,"node":self.x["comparison_node"],"pod":"comparison-pod"},"values":[[1794564240,"1024"]]}]
            # Honor explicit pod/node filters. A healthy-peer read cannot verify affected telemetry.
            if any(f'{k}="' in query and f'{k}="{labels[k]}"' not in query for k in ("pod","node","namespace")):
                result=result[1:];historical=False
            tag="host_memory" if metric.startswith("container_") else "device_used" if metric.endswith("USED") else "device_free" if metric.endswith("FREE") else "device_util"
            return {"status":"success","data":{"resultType":"matrix","result":result}},{tag:[str(val)]} if historical else {}
        if url.hostname=="payments.example.test": return "HTTP/1.1 200 OK\ncurrent probe dns=0.002 connect=0.003 ttfb=0.020",{}
        if url.port==19400: return "DCGM_FI_DEV_FB_USED{gpu=\"0\"} 1024\nDCGM_FI_DEV_FB_FREE{gpu=\"0\"} 79976\n",{}
        raise WorldError("MockNotImplemented","HTTP destination outside modeled evidence sources",0,2)


def mutation(tool,argv):
    if tool not in ("az","kubectl"): return False
    words,_,tail=parse(argv,tool)
    if tool=="kubectl": return bool(words) and words[0] in {"apply","patch","delete","create","scale","rollout","drain","cordon","uncordon","edit","replace","set","run"}
    return any(w in {"update","create","delete","scale","upgrade","stop","start","add","register"} for w in words)
