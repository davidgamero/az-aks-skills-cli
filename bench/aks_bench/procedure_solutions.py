"""Host-only reference procedures and assessment. Never provided to agents."""

import copy
import json

from .candidate_solutions import kube, patch, apply
from .candidate_fixtures import key
from .procedure_oracles import snat_target


def backup_assessment(s):
    # Reference differs from oracle field evaluation: labels describe primary fixtures.
    names={p["metadata"]["name"] for p in s["initial_state"]["clusters"][0]["_world"]["resources"].values() if p["kind"]=="PersistentVolume"}
    fields={"orders":[],"archive":["sizeGiB"],"private":["networkAccessPolicy"],"encrypted":["diskEncryptionSetId"],"files":["backupTier"],"legacy":["driver"],"static":["storageClassName"]}
    return {"volumes":[{"name":n,"eligible":not fields[s["procedure_reference_names"][n]],"blockers":fields[s["procedure_reference_names"][n]]} for n in sorted(names)],"worst_case_rpo_hours":36}


def commands(s):
    name=s["name"];x=s["context"]
    if name=="procedure-snat-surge-budget":
        ports,ips=snat_target(s)
        return [["aks","show","-g",x["resource_group"],"-n",x["cluster"]],
            ["aks","update","-g",x["resource_group"],"-n",x["cluster"],"--load-balancer-outbound-ports",str(ports),"--load-balancer-managed-outbound-ip-count",str(ips)],
            ["network","lb","outbound-rule","list","-g",s["state"]["clusters"][0]["nodeResourceGroup"],"--lb-name","kubernetes"]]
    if name=="procedure-coredns-import-reload":
        cm=copy.deepcopy(s["state"]["clusters"][0]["_world"]["resources"][key("configmap","kube-system","coredns-custom")])
        cm["data"]["private.server"]=cm["data"].pop("private.conf")
        return [apply(cm),kube("rollout","restart","deployment/coredns","-n","kube-system"),
            *[kube("exec","deployment/api","-n","retail","--","nslookup",q) for q in [x["private_query"],*x["preserve_queries"]]]]
    if name=="procedure-disk-expand-boundary":
        result=[]
        offline=s["state"]["clusters"][0]["_world"]["disk"]["sku"]["name"]=="Premium_LRS"
        if offline:result.append(kube("scale","deployment/api","-n","retail","--replicas=0"))
        result.append(patch("pvc","data",{"spec":{"resources":{"requests":{"storage":"5120Gi"}}}}))
        if offline:result.append(kube("scale","deployment/api","-n","retail","--replicas=1"))
        return result+[kube("get","pvc/data","-o","json"),kube("exec","deployment/api","--","df","-BG","/mnt/data")]
    return [["dataprotection","backup-vault","show","-g",x["resource_group"],"--vault-name",x["backup_vault"]],
        kube("get","pv","-o","json"),["disk","list","-g",x["resource_group"]],{"reference_procedure_plan":True}]
