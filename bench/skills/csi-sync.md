# Repair CSI synchronization without copying secret contents

Inspect the SecretProviderClass, actual pod volume/mount and namespace references.
A SecretProviderClass alone does not synchronize a Kubernetes Secret: there must
be a live pod mounting it. If access and mount already work, avoid reassigning roles.

Compare `parameters.objects` objectName/objectAlias to each `secretObjects.data`
entry. The synchronization objectName must match the **mounted filename/alias**.
For an objectAlias, use that alias rather than the Key Vault source object's name.
Retain the required secretName, type and data keys.

```sh
kubectl get secretproviderclass CLASS -n NAMESPACE -o yaml
kubectl get deployment DEPLOYMENT -n NAMESPACE -o yaml
kubectl apply -f corrected-secret-provider-class.yaml
```

Preserve the consumer mount, identity and permissions. If mount itself fails,
inspect provider/CSI logs on the affected node and classify identity, private DNS
or namespace/reference errors. Verify synchronized Secret metadata/keys and actual
application consumption using a nonsecret version/status probe. Manually writing
the vault value into a Secret is not a synchronization repair.

Sources:
- https://learn.microsoft.com/en-us/azure/aks/csi-secrets-store-configuration-options
- https://learn.microsoft.com/en-us/troubleshoot/azure/azure-kubernetes/extensions/troubleshoot-key-vault-csi-secrets-store-csi-driver
