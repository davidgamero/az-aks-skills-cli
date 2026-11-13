# Schedule AKS Automatic maintenance

Use for schedule changes, not immediate upgrades. Automatic keeps stable/NodeImage
channels. Reuse the current maintenanceconfiguration list, or obtain it once.
Select the exact child resource:

- `aksManagedAutoUpgradeSchedule`: Kubernetes auto-upgrades.
- `aksManagedNodeOSUpgradeSchedule`: node OS/image auto-upgrades.
- `default`: platform/component releases; this does not replace the other two.

For each requested window, choose update if present or add if absent. After
checking inputs, put both independent updates and the final list in one shell
call, joining commands with &&. A weekly update has this form:

```sh
az aks maintenanceconfiguration update -g RG --cluster-name CLUSTER -n CONFIGURATION --schedule-type Weekly --day-of-week DAY --interval-weeks 1 --duration HOURS --start-time HH:MM --utc-offset OFFSET -o none
```

Finish with `az aks maintenanceconfiguration list -g RG --cluster-name CLUSTER`.
One list verifies both target schedules and the unchanged default; aks show
does not return these child resources. Reuse any existing cluster/channel check
instead of repeating it around each child update. Do not alter unrelated settings.

Use the user's dates/times, duration and offset. Duration is hours, not an end-time
field, and must be at least four hours. Skip a window already matching the request.
Maintenance is best effort; urgent work can bypass windows and in-flight work may
finish after closure.

Sources:
- https://learn.microsoft.com/en-us/azure/aks/planned-maintenance
- https://learn.microsoft.com/en-us/azure/aks/intro-aks-automatic
