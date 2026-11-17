"""Guide-derived operational procedures: seeded inputs, no answers in prompts."""

import copy
import json
import random
import hashlib

from .candidate_fixtures import obj, put, key

NAMES = ("procedure-snat-surge-budget", "procedure-coredns-import-reload", "procedure-disk-expand-boundary", "procedure-backup-region-eligibility")
SKILLS = dict(zip(NAMES, ("aks-snat-capacity-plan", "aks-coredns-customize", "aks-disk-expand-safely", "aks-backup-restore-assess")))


def make(name, seed, base):
    s = copy.deepcopy(base)
    c = s["state"]["clusters"][0]; w = c["_world"]; rng = random.Random(seed)
    old_context = s["context"]
    x = {"cluster":c["name"], "resource_group":c["resourceGroup"], "namespace":"retail", "deployment":"api",
         "developer_object_id":old_context["developer_object_id"], "authorization":"Change only the named task resources; preserve unrelated settings.",
         "verification":"Use ordinary Azure/Kubernetes reads and workload probes; do not just describe a solution."}
    if name == NAMES[0]:
        c["networkProfile"]["outboundType"] = "loadBalancer"
        c["networkProfile"]["loadBalancerProfile"] = {"allocatedOutboundPorts":0,"managedOutboundIPs":{"count":1},"idleTimeoutInMinutes":30}
        for i,pool in enumerate(c["agentPoolProfiles"]):
            pool.update(count=3 if i==0 else rng.choice([12,17]), enableAutoScaling=i>0,
                        maxCount=None if i==0 else rng.choice([83,97,113]), upgradeSettings={"maxSurge":"1" if i==0 else "33%"})
        x.update(minimum_ports_per_node=rng.choice([1973,3001,3997]), maximum_outbound_ips=12,
                 planning_policy="Cover every pool at its autoscaler maximum (fixed count for non-autoscaled pools), with each pool's rounded-up surge concurrently at that maximum. Choose the smallest supported per-node port allocation meeting demand and the fewest managed outbound IPs that cover this envelope. Dedicated outbound frontends have no inbound rules consuming ports.")
        task="Configure the cluster's existing egress to meet the approved per-node connection budget throughout the specified growth and upgrade envelope. Minimize the added public IPs, preserve pool settings and the idle timeout, and verify the effective configuration."
    elif name == NAMES[1]:
        x.update(private_zone=f"corp{seed}.internal", private_query=f"ledger.corp{seed}.internal", approved_dns_upstream="10.2.0.4",
                 private_answer="10.2.3.8", preserve_queries=["kubernetes.default.svc.cluster.local","www.microsoft.com"],
                 authorization="Repair the existing custom DNS configuration and reload CoreDNS if needed. Retain the AKS-managed main configuration and unrelated customizations; do not replace DNS or add pod-specific host mappings.")
        main=put(w,obj("ConfigMap","coredns","kube-system",data={"Corefile":".:53 {\n errors\n kubernetes cluster.local\n forward . /etc/resolv.conf\n import custom/*.override\n}\nimport custom/*.server\n"}))
        main["metadata"]["labels"]={"addonmanager.kubernetes.io/mode":"Reconcile"}
        put(w,obj("ConfigMap","coredns-custom","kube-system",data={"legacy.server":"legacy.internal:53 {\n forward . 10.2.0.5\n}\n",
             "private.conf":f"{x['private_zone']}:53 {{\n errors\n cache 30\n forward . {x['approved_dns_upstream']}\n}}\n"}))
        put(w,obj("Deployment","coredns","kube-system",{"replicas":2,"selector":{"matchLabels":{"k8s-app":"kube-dns"}},"template":{"metadata":{"labels":{"k8s-app":"kube-dns"}},"spec":{"containers":[{"name":"coredns","image":"mcr.microsoft.com/oss/kubernetes/coredns:v1.12.0"}]}}},status={"readyReplicas":2,"replicas":2}))
        put(w,obj("Service","kube-dns","kube-system",{"clusterIP":"10.100.0.10","selector":{"k8s-app":"kube-dns"},"ports":[{"port":53,"protocol":"UDP"},{"port":53,"protocol":"TCP"}]}))
        for i in range(2):
            pod=put(w,obj("Pod",f"coredns-{i}","kube-system",{"containers":[{"name":"coredns","image":"mcr.microsoft.com/oss/kubernetes/coredns:v1.12.0"}]},status={"phase":"Running","conditions":[{"type":"Ready","status":"True"}]}))
            pod["metadata"]["labels"]={"k8s-app":"kube-dns"}
        w["dns_loaded"]={"legacy.server":w["resources"][key("configmap","kube-system","coredns-custom")]["data"]["legacy.server"]}
        task="Restore resolution of the private ledger hostname. Direct queries to its approved upstream succeed, but normal pod DNS does not. Make the repair survive AKS reconciliation while retaining existing cluster, external and legacy DNS behavior. Verify the affected and preserved paths."
    elif name == NAMES[2]:
        sku="Premium_LRS" if seed%2 else "PremiumV2_LRS"
        x.update(pvc="data",pv="data-volume",disk="data-disk",mount_path="/mnt/data",target_size_gib=5120,
                 authorization="Expand this existing CSI volume to the approved size. A maintenance window permits scaling only api to zero if required by the observed disk type; avoid downtime if that type supports the requested expansion online. Restore the original replica count and preserve disk/PV/PVC identities and data.")
        c["kubernetesVersion"]=c["currentKubernetesVersion"]="1.35.0"
        w["resources"][key("deployment","retail","api")]["spec"]["replicas"]=1
        podspec=w["resources"][key("deployment","retail","api")]["spec"]["template"]["spec"]
        podspec["nodeName"]="apps-0"
        podspec["volumes"].append({"name":"data","persistentVolumeClaim":{"claimName":"data"}})
        podspec["containers"][0]["volumeMounts"].append({"name":"data","mountPath":"/mnt/data"})
        pvc=w["resources"][key("persistentvolumeclaim","retail","data")]
        pvc["spec"].update(volumeName="data-volume",storageClassName="application-disk");pvc["spec"]["resources"]["requests"]["storage"]="3072Gi"
        pvc["status"].update(capacity={"storage":"3072Gi"})
        sc=put(w,obj("StorageClass","application-disk","",provisioner="disk.csi.azure.com",allowVolumeExpansion=True,parameters={"skuName":sku,"cachingMode":"None"}))
        sc["apiVersion"]="storage.k8s.io/v1"
        disk_id=c["id"].split("/providers/")[0]+"/providers/Microsoft.Compute/disks/data-disk"
        put(w,obj("PersistentVolume","data-volume","",{"capacity":{"storage":"3072Gi"},"storageClassName":"application-disk","persistentVolumeReclaimPolicy":"Retain","accessModes":["ReadWriteOnce"],"claimRef":{"name":"data","namespace":"retail"},"csi":{"driver":"disk.csi.azure.com","volumeHandle":disk_id}},status={"phase":"Bound"}))
        ledger=f"synthetic ledger seed={seed}; entries=100; balance=12000\n"
        checksum=hashlib.sha256(ledger.encode()).hexdigest()
        w["disk_files"]={"/mnt/data/ledger.txt":ledger,"/mnt/data/ledger.checksum":checksum+"\n"}
        w["disk"]={"id":disk_id,"name":"data-disk","resourceGroup":c["resourceGroup"],"sku":{"name":sku},"diskSizeGb":3072,"diskState":"Attached","dataHash":checksum}
        w["filesystem_gib"]=3072;w["downtime_seen"]=False
        task="Expand the application's existing disk-backed volume to the approved target using the appropriate procedure for the actual disk type. Preserve data and resource identities, avoid unnecessary downtime, restore the workload and verify capacity from inside it."
    else:
        x.update(authorization="Read-only assessment; do not modify backup, disks, access controls or workloads.",
                 backup_vault="production-vault",target_region="westus",source_region="eastus",
                 report_schema={"volumes":[{"name":"PV name","eligible":"boolean for Vault-tier paired-region restore","blockers":["violated field names: driver, sizeGiB, networkAccessPolicy, diskEncryptionSetId, backupTier, storageClassName"]}],"worst_case_rpo_hours":"documented combined worst case for eligible disk recovery points in the paired region"},report_path="/work/assessment.json")
        w["vault_backup"]={"name":"production-vault","location":"eastus","properties":{"storageSettings":[{"datastoreType":"VaultStore","type":"GeoRedundant"}],"featureSettings":{"crossRegionRestoreSettings":{"state":"Enabled"}}}}
        w["backup_disks"]=[]
        reference_names={}
        for index,(label,options) in enumerate((("orders",{}),("archive",{"sizeGiB":2048}),("private",{"networkAccessPolicy":"DenyAll"}),
                              ("encrypted",{"diskEncryptionSetId":"/subscriptions/synthetic/resourceGroups/rg/providers/Microsoft.Compute/diskEncryptionSets/customer"}),
                              ("files",{"driver":"file.csi.azure.com"}),("legacy",{"driver":"kubernetes.io/azure-disk"}),("static",{"storageClassName":""}))):
            values={"sizeGiB":rng.choice([128,256,512]),"networkAccessPolicy":"AllowAll","diskEncryptionSetId":None,"driver":"disk.csi.azure.com","storageClassName":"application-disk",**options}
            volume_name=f"volume-{seed}-{index}";reference_names[volume_name]=label
            handle=c["id"].split("/providers/")[0]+"/providers/Microsoft.Compute/disks/"+volume_name
            volume=put(w,obj("PersistentVolume",volume_name,"",{"capacity":{"storage":str(values["sizeGiB"])+"Gi"},"storageClassName":values["storageClassName"],"csi":{"driver":values["driver"],"volumeHandle":handle},"persistentVolumeReclaimPolicy":"Retain"},status={"phase":"Bound"}))
            if label=="legacy":
                volume["spec"].pop("csi");volume["spec"]["azureDisk"]={"diskName":volume_name,"dataDiskURI":handle,"kind":"Managed"}
            if label=="static":volume["spec"].pop("storageClassName")
            if label=="files":volume["spec"]["csi"].update(volumeHandle=f"backup-rg#storage{seed}#share",volumeAttributes={"protocol":"smb"})
            else:w["backup_disks"].append({"id":handle,"name":volume_name,"diskSizeGb":values["sizeGiB"],"publicNetworkAccess":"Enabled","networkAccessPolicy":values["networkAccessPolicy"],"dataAccessAuthMode":"None","encryption":{"diskEncryptionSetId":values["diskEncryptionSetId"]}})
        s["procedure_reference_names"]=reference_names
        w["resources"].pop(key("persistentvolumeclaim","retail","data"))
        task="Assess whether each inventoried persistent volume can be protected in the selected vault tier for recovery in the requested paired region. Identify every blocking field without weakening security controls, and report the documented worst-case recovery-point age. Write the assessment in the supplied schema; do not perform a restore or change resources."
    s.update(name=name,seed=seed,suite="procedure-v1",variant="primary",context=x,prompt=f"Operate on AKS cluster {c['name']} in resource group {c['resourceGroup']}. {task} Approved targets, limits and output requirements are in /work/task-context.json. The CLI is authenticated and kubectl is configured.",
             workspace_files={"task-context.json":json.dumps(x,indent=2)},faults=[],responses=[],procedure_skill=SKILLS[name])
    from .procedure_runtime import ProcedureWorld
    ProcedureWorld(s,s["state"]).reconcile()
    s["initial_state"]=copy.deepcopy(s["state"])
    return s
