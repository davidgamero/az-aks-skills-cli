# Schedule AKS Automatic maintenance

Automatic uses the stable Kubernetes upgrade channel and NodeImage node OS
channel. Adjust maintenance schedules without disabling those channels or
initiating an immediate upgrade.

Inspect existing child resources once:

```sh
az aks maintenanceconfiguration list --resource-group RG --cluster-name CLUSTER
```

Select the configuration by the kind of upgrade:

- `aksManagedAutoUpgradeSchedule`: Kubernetes auto-upgrades.
- `aksManagedNodeOSUpgradeSchedule`: node OS/image auto-upgrades.
- `default`: platform/component releases; this does not replace the other two.

For each requested weekly window, use `update` if the resource exists, or `add`
if absent. Substitute the user's day, start time, UTC offset and duration:

```sh
az aks maintenanceconfiguration update --resource-group RG --cluster-name CLUSTER --name CONFIGURATION --schedule-type Weekly --day-of-week DAY --interval-weeks 1 --duration HOURS --start-time HH:MM --utc-offset +00:00
```

Durations must be at least four hours; a window from 02:00 to 06:00 is duration 4,
not an end-time parameter. Keep unrelated schedules and other cluster settings
unchanged. Verify both target child resources with a final maintenanceconfiguration
list or individual show calls; aks show alone does not return their schedules.

Maintenance windows are best-effort scheduling preferences. Urgent/reactive
maintenance can occur outside them, and work started within a window can finish
after it closes.

Sources:
- https://learn.microsoft.com/en-us/azure/aks/planned-maintenance
- https://learn.microsoft.com/en-us/azure/aks/intro-aks-automatic
