"""Versioned command affordances for the bounded candidate resource model."""

COMMON = "--resource-group --name --query --output --subscription --only-show-errors --help -h --yes -y --no-wait"
OPTIONS = {
    "aks namespace": "--cluster-name --cpu-request --cpu-limit --memory-request --memory-limit --ingress-policy --egress-policy --adoption-policy --delete-policy --labels --annotations --file --admin --overwrite-existing",
    "aks maintenanceconfiguration": "--cluster-name --schedule-type --day-of-week --interval-weeks --duration --start-time --utc-offset --start-date",
    "aks identity-binding": "--cluster-name",
    "aks safeguards": "--cluster-name --level --excluded-ns",
    "aks addon": "--cluster-name --addon --enable-secret-rotation --rotation-poll-interval",
    "aks nodepool": "--cluster-name --kubernetes-version --node-count --max-surge",
    "aks": "--acr --file --overwrite-existing --admin --pod-cidr --api-server-authorized-ip-ranges --enable-oidc-issuer --enable-workload-identity --enable-gateway-api --enable-app-routing-istio --attach-acr --kubernetes-version --control-plane-only",
    "role assignment": "--assignee --assignee-object-id --assignee-principal-type --role --scope --condition --condition-version --include-inherited --all",
    "role definition": "--name --scope",
    "identity federated-credential": "--identity-name --issuer --subject --audiences --audience",
    "identity": "",
    "acr": "--public-network-enabled --admin-enabled --role-assignment-mode --repository --image --ignore-errors",
    "keyvault": "--vault-name --id --version",
    "network nsg": "--nsg-name --access --direction --protocol --priority --source-address-prefixes --destination-address-prefixes --source-port-ranges --destination-port-ranges",
    "network private-dns": "--zone-name",
    "vm": "--location --all --size",
    "account": "",
    "group": "--location",
    "provider": "--namespace --wait",
    "monitor": "--resource-id --offset --status --max-events",
    "deployment group": "",
    "version": "",
}
COMMANDS = {
    "aks namespace": "add update delete show list get-credentials",
    "aks identity-binding": "show list",
    "aks safeguards": "show update",
    "aks addon": "show update",
    "identity federated-credential": "show list create update delete",
    "role assignment": "show list create delete",
    "network nsg rule": "show list create update",
}


def options_for(command):
    return next((set((COMMON + " " + options).split()) for prefix, options in OPTIONS.items()
                 if command == prefix or command.startswith(prefix + " ")), set(COMMON.split()))


def help_text(command):
    if command in COMMANDS:
        return f"Group: az {command}\nCommands:\n" + "".join(f"    {c}\n" for c in COMMANDS[command].split())
    if command in OPTIONS and command not in ("aks", "version"):
        return f"Group: az {command}\nUse a subcommand and --help for arguments.\n"
    if command == "aks": return None
    if any(command.startswith(prefix + " ") for prefix in OPTIONS):
        text = f"Command: az {command}\nArguments:\n" + "".join(f"    {o}\n" for o in sorted(options_for(command)))
        if command.startswith("aks namespace"):
            text += "\nAdoption: Never, IfIdentical, Always. Delete policy: Keep, Delete.\nIngress: AllowSameNamespace, AllowAll, DenyAll. Egress: AllowAll, DenyAll.\n"
        if command.startswith("aks maintenanceconfiguration"):
            text += "\nWeekly schedule: --day-of-week DAY --interval-weeks N --duration HOURS (4-24) --start-time HH:MM --utc-offset +HH:MM\n"
        return text
    return None
