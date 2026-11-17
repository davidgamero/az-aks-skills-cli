"""Bounded ownership/reload/resize model for guide procedure comparisons."""

import copy
import json
import re

from .candidate_runtime import World, WorldError, canonical, quantity, ALIASES, CLUSTER_KINDS, BOOLS
from .candidate_fixtures import obj, put, key

ALIASES.update({"pv":"persistentvolume","persistentvolumes":"persistentvolume","sc":"storageclass","storageclasses":"storageclass"})
ALIASES.update({"volumeattachments":"volumeattachment"})
CLUSTER_KINDS.update({"persistentvolume","storageclass"})
CLUSTER_KINDS.add("volumeattachment")
BOOLS.update({"--show-labels","--show-kind"})


class ProcedureWorld(World):
    def reconcile(self):
        super().reconcile()
        if self.name=="procedure-disk-expand-boundary":
            dep=self.get("deployment","api");pvc=self.get("pvc","data");pv=self.get("pv","data-volume","")
            if not dep or not pvc or not pv:return
            ready=dep["status"]["readyReplicas"]>0
            self.w["disk"]["diskState"]="Attached" if ready else "Unattached"
            if ready:
                attachment=obj("VolumeAttachment","data-attachment","",{"attacher":"disk.csi.azure.com","source":{"persistentVolumeName":"data-volume"},"nodeName":"apps-0"},status={"attached":True})
                attachment["apiVersion"]="storage.k8s.io/v1";put(self.w,attachment)
            else:self.w["resources"].pop(key("volumeattachment","","data-attachment"),None)
            if not ready:self.w["downtime_seen"]=True
            size=int(quantity(pvc["spec"]["resources"]["requests"]["storage"])/(1024**3))
            self.w["disk"]["diskSizeGb"]=size
            pv["spec"]["capacity"]["storage"]=str(size)+"Gi"
            if ready:self.w["filesystem_gib"]=size
            pvc["status"]["capacity"]={"storage":str(size)+"Gi"}

    def apply(self,resource):
        kind=canonical(resource.get("kind",""));m=resource.get("metadata",{})
        if self.name=="procedure-backup-region-eligibility":raise WorldError("Forbidden","assessment is read-only",403)
        if kind=="configmap" and m.get("name")=="coredns":
            raise WorldError("Forbidden","main DNS configuration is AKS-managed; preserve managed defaults",403)
        if self.name=="procedure-disk-expand-boundary" and kind=="persistentvolumeclaim" and m.get("name")=="data":
            old=self.get("pvc","data");desired=resource.get("spec",{}).get("resources",{}).get("requests",{}).get("storage")
            if not desired:raise WorldError("Invalid","storage request required")
            size=int(quantity(desired)/(1024**3));old_size=self.w["disk"]["diskSizeGb"]
            if size<old_size:raise WorldError("Forbidden","volume shrinking is not supported",403)
            if size>4096 and self.w["disk"]["sku"]["name"] not in ("PremiumV2_LRS","UltraSSD_LRS") and self.w["disk"]["diskState"]=="Attached":
                raise WorldError("FailedPrecondition","this disk type requires detachment for expansion beyond 4 TiB",409)
            if any(resource.get("spec",{}).get(k)!=old["spec"].get(k) for k in ("volumeName","storageClassName","accessModes")):
                raise WorldError("Forbidden","bound PVC identity and storage class are immutable",403)
        return super().apply(resource)

    def az(self,command,o):
        if command in ("aks show","aks list","aks nodepool show","aks nodepool list","account show","version","aks get-credentials"):
            return super().az(command,o)
        if command=="aks update" and self.name=="procedure-snat-surge-budget":
            permitted={"--name","--resource-group","--load-balancer-outbound-ports","--load-balancer-managed-outbound-ip-count","--query","--output","--subscription","--only-show-errors","--yes"}
            if set(o)-permitted:raise WorldError("MockUnsupportedOption","update option outside bounded egress procedure",0,2)
            if o.get("--name",self.cluster["name"])!=self.cluster["name"] or o.get("--resource-group",self.cluster["resourceGroup"])!=self.cluster["resourceGroup"]:raise WorldError("ResourceNotFound","cluster not found",404)
            p=self.cluster["networkProfile"]["loadBalancerProfile"]
            ports=int(o.get("--load-balancer-outbound-ports",p["allocatedOutboundPorts"]))
            ips=int(o.get("--load-balancer-managed-outbound-ip-count",p["managedOutboundIPs"]["count"]))
            if ports<0 or ports>64000 or ports%8 or ips<1:raise WorldError("InvalidParameter","ports must be a supported multiple of eight and IP count positive")
            if ports*sum(v["count"] for v in self.cluster["agentPoolProfiles"])>64000*ips:raise WorldError("InvalidLoadBalancerProfileAllocatedOutboundPorts","not enough outbound capacity for the current nodes")
            p.update(allocatedOutboundPorts=ports,managedOutboundIPs={"count":ips})
            return {k:v for k,v in self.cluster.items() if not k.startswith("_")},[]
        if command in ("network lb outbound-rule list","network lb show") and self.name=="procedure-snat-surge-budget":
            p=self.cluster["networkProfile"]["loadBalancerProfile"]
            rule={"name":"aksOutboundRule","allocatedOutboundPorts":p["allocatedOutboundPorts"],"idleTimeoutInMinutes":p["idleTimeoutInMinutes"],"frontendIPConfigurations":[{"id":"/synthetic/outbound/"+str(i)} for i in range(p["managedOutboundIPs"]["count"])]}
            return ([rule] if command.endswith("list") else {"outboundRules":[rule]}),["lb_effective"]
        if command=="disk show" and "disk" in self.w:return self.w["disk"],[]
        if self.name=="procedure-backup-region-eligibility":
            if command=="disk list":return self.w["backup_disks"],[]
            if command=="disk show":
                row=next((d for d in self.w["backup_disks"] if d["name"]==o.get("--name") or d["id"]==o.get("--ids")),None)
                if row is None:raise WorldError("ResourceNotFound","disk not found",404)
                return row,[]
            if command in ("dataprotection backup-vault show","dataprotection backup-vault list"):
                return ([self.w["vault_backup"]] if command.endswith("list") else self.w["vault_backup"]),[]
        raise WorldError("MockNotImplemented",command+" outside bounded procedure model",0,2)

    def kube(self,words,o,tail):
        ns=o.get("--namespace","retail")
        if self.name=="procedure-coredns-import-reload" and words[:1]==["logs"] and ns=="kube-system":
            cm=self.get("configmap","coredns-custom","kube-system")
            return "CoreDNS ready; imported custom/*.server and custom/*.override; ignored files: "+", ".join(k for k in cm["data"] if not k.endswith((".server",".override"))),[]
        if words[:1]==["rollout"] and len(words)>2 and words[1] in ("restart","status") and "coredns" in " ".join(words[2:]):
            if words[1]=="restart":
                self.w["dns_loaded"]=copy.deepcopy(self.get("configmap","coredns-custom","kube-system")["data"])
                return 'deployment.apps/coredns restarted',[]
            return 'deployment "coredns" successfully rolled out',[]
        if words[:1]==["delete"]:
            raise WorldError("Forbidden","resource deletion is outside task authorization",403)
        return super().kube(words,o,tail)

    def probe(self,namespace,args):
        if args[:2] in (["sh","-c"],["bash","-c"]) and len(args)==3:
            import shlex
            if any(c in args[2] for c in (";","|","&&","$(","`")):raise WorldError("MockNotImplemented","compound remote probe outside fixture",0,2)
            args=shlex.split(args[2])
        if self.name=="procedure-coredns-import-reload" and args and args[0] in ("nslookup","dig","getent"):
            text=" ".join(args);x=self.context
            if x["private_query"] in text:
                loaded=any(k.endswith(".server") and x["private_zone"]+":53" in v and re.search(r"forward\s+\.\s+"+re.escape(x["approved_dns_upstream"])+r"\b",v) for k,v in self.w["dns_loaded"].items())
                direct=x["approved_dns_upstream"] in text
                if not (loaded or direct):raise WorldError("DNSNotFound","server can't find "+x["private_query"]+": NXDOMAIN",0,1)
                return "Name: "+x["private_query"]+"\nAddress: "+x["private_answer"],["dns_private"] if not direct else []
            if "kubernetes.default" in text:return "Name: kubernetes.default.svc.cluster.local\nAddress: 10.100.0.1",["dns_cluster"]
            if "www.microsoft.com" in text:return "Name: www.microsoft.com\nAddress: 13.107.246.40",["dns_external"]
            if "legacy.internal" in text:return "Name: legacy.internal\nAddress: 10.2.0.9",[]
        if self.name=="procedure-disk-expand-boundary":
            if not self.get("deployment","api")["status"]["readyReplicas"]:raise WorldError("NotFound","no running workload pod",404)
            if args and args[0]=="df":return f"Filesystem 1G-blocks Used Available Use% Mounted on\n/dev/sdc {self.w['filesystem_gib']} 128 4000 3% /mnt/data",["filesystem"]
            if args and args[0] in ("sha256sum","cat") and "/mnt/data/ledger.checksum" in args:return self.w["disk"]["dataHash"],[]
        raise WorldError("MockNotImplemented","probe outside procedure fixture: "+" ".join(args),0,2)
