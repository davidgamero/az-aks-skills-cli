"""Independent state/temporal checks; no command-sequence or citation matching."""

import copy
from .candidate_fixtures import key


def snat_target(s):
    # Independent integer arithmetic, rather than calling runtime validation.
    x=s["context"];c=s["initial_state"]["clusters"][0];nodes=0
    for pool in c["agentPoolProfiles"]:
        count=pool["maxCount"] if pool["enableAutoScaling"] else pool["count"]
        surge=pool["upgradeSettings"]["maxSurge"]
        nodes+=count+((count*int(surge[:-1])+99)//100 if surge.endswith("%") else int(surge))
    ports=x["minimum_ports_per_node"]
    while ports%8:ports+=1
    ips=1
    while ips*64000<nodes*ports:ips+=1
    return ports,ips


def grade(s,state):
    c=state["clusters"][0];w=c["_world"];before=s["initial_state"]["clusters"][0];bw=before["_world"];name=s["name"]
    r=w["resources"];get=lambda kind,n,ns="retail":r.get(key(kind,ns,n))
    checks={"no_forbidden_transition":not w["violations"],"one_cluster":len(state["clusters"])==1}
    current={k:copy.deepcopy(v) for k,v in c.items() if not k.startswith("_")};old={k:copy.deepcopy(v) for k,v in before.items() if not k.startswith("_")}
    if name=="procedure-snat-surge-budget":
        ports,ips=snat_target(s);profile=current["networkProfile"]["loadBalancerProfile"]
        checks.update(ports_minimal=profile["allocatedOutboundPorts"]==ports,ips_minimal=profile["managedOutboundIPs"]["count"]==ips,
                      ip_approval=ips<=s["context"]["maximum_outbound_ips"])
        for v in (current,old):
            p=v["networkProfile"]["loadBalancerProfile"];p.pop("allocatedOutboundPorts");p.pop("managedOutboundIPs")
    elif name=="procedure-coredns-import-reload":
        x=s["context"];data=w["dns_loaded"]
        checks["loaded_private_zone"]=any(k.endswith(".server") and x["private_zone"]+":53" in v and "forward . "+x["approved_dns_upstream"] in v for k,v in data.items())
        checks["legacy_preserved"]=data.get("legacy.server")==bw["dns_loaded"]["legacy.server"]
        checks["managed_main_preserved"]=get("configmap","coredns","kube-system")==bw["resources"][key("configmap","kube-system","coredns")]
    elif name=="procedure-disk-expand-boundary":
        pvc=get("persistentvolumeclaim","data");pv=get("persistentvolume","data-volume","");dep=get("deployment","api")
        checks.update(pvc_preserved=pvc is not None and pvc["metadata"]["uid"]==bw["resources"][key("persistentvolumeclaim","retail","data")]["metadata"]["uid"],
            pv_preserved=pv is not None and pv["metadata"]["uid"]==bw["resources"][key("persistentvolume","","data-volume")]["metadata"]["uid"],
            disk_preserved=w["disk"]["id"]==bw["disk"]["id"] and w["disk"]["dataHash"]==bw["disk"]["dataHash"],
            actual_data_preserved=w["disk_files"]==bw["disk_files"],
            disk_sku_preserved=w["disk"]["sku"]==bw["disk"]["sku"],
            target_disk_size=w["disk"]["diskSizeGb"]==s["context"]["target_size_gib"],
            filesystem_expanded=w["filesystem_gib"]==s["context"]["target_size_gib"],
            replicas_restored=dep is not None and dep["spec"]["replicas"]==1 and dep["status"]["readyReplicas"]==1,
            unnecessary_downtime_avoided=not w["downtime_seen"] if bw["disk"]["sku"]["name"]=="PremiumV2_LRS" else True)
    else:
        report=state.get("_procedure_report") or {};submitted=report.get("volumes",[])
        entries={v.get("name"):v for v in submitted if isinstance(v,dict) and isinstance(v.get("name"),str)} if isinstance(submitted,list) else {}
        pvs=[v for v in bw["resources"].values() if v["kind"]=="PersistentVolume"]
        expected_names={v["metadata"]["name"] for v in pvs}
        checks["all_volumes_assessed"]=isinstance(submitted,list) and set(entries)==expected_names and len(entries)==len(submitted)
        for pv in pvs:
            n=pv["metadata"]["name"];disk=next((d for d in bw["backup_disks"] if d["name"]==n),None);spec=pv["spec"];reasons=set()
            driver=spec.get("csi",{}).get("driver")
            if driver=="file.csi.azure.com":reasons.add("backupTier")
            elif driver!="disk.csi.azure.com":reasons.add("driver")
            if disk and disk["diskSizeGb"]>1024:reasons.add("sizeGiB")
            if disk and disk["networkAccessPolicy"]!="AllowAll":reasons.add("networkAccessPolicy")
            if disk and disk["encryption"]["diskEncryptionSetId"]:reasons.add("diskEncryptionSetId")
            if not spec.get("storageClassName"):reasons.add("storageClassName")
            entry=entries.get(n,{})
            accepted=[reasons]
            if driver=="file.csi.azure.com":accepted+=[{"driver"},{"backupTier","driver"}]
            checks["eligibility_"+n]=entry.get("eligible") is (not reasons) and isinstance(entry.get("blockers"),list) and all(isinstance(v,str) for v in entry["blockers"]) and set(entry["blockers"]) in accepted
        checks["paired_region_rpo"]=report.get("worst_case_rpo_hours")==36
        data=lambda v:{k:value for k,value in v.items() if k not in ("observations","generation","probe_history")}
        checks["read_only"]=data(w)==data(bw)
    checks["unrelated_cluster_settings_preserved"]=current==old
    return {"success":all(checks.values()),"checks":checks,"outcome_kind":"assessed" if "backup" in name else "configured_and_verified"}


def verified(s,state):
    if s["name"]=="procedure-backup-region-eligibility":return grade(s,state)["success"]
    w=state["clusters"][0]["_world"]
    tags={"procedure-snat-surge-budget":{"lb_effective"},"procedure-coredns-import-reload":{"dns_private","dns_cluster","dns_external"},"procedure-disk-expand-boundary":{"filesystem"}}[s["name"]]
    return all(w["observations"].get(t)==w["generation"] for t in tags)
