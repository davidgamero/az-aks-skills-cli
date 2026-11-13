# Publish through the managed application-routing Gateway API

Inspect AKS version, ingressProfile, GatewayClasses, existing Gateways/HTTPRoutes
and backend Service endpoints. New Automatic 1.36+ clusters can have prerequisites
preconfigured; existing clusters do not necessarily acquire all new defaults.
Reuse supported managed features. Check mesh/CRD conflicts before enabling missing
components with the installed CLI's help.

The application-routing class is **approuting-istio**, not the mesh class `istio`.
Reuse a suitable programmed HTTP listener or create the approved Gateway. Attach
an HTTPRoute with the approved hostname/path and the Service's exposed port:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: application-route
  namespace: NAMESPACE
spec:
  parentRefs:
  - name: GATEWAY
  hostnames: [APPROVED_HOSTNAME]
  rules:
  - matches:
    - path: {type: PathPrefix, value: APPROVED_PATH}
    backendRefs:
    - {name: SERVICE, port: SERVICE_PORT}
```

Verify Programmed, Accepted and ResolvedRefs conditions, ready backend endpoints
and an HTTP request with the correct Host header and path. Preserve old working
routes/listeners until an explicitly authorized cutover. Resource creation alone
does not prove traffic reaches the application.

Sources:
- https://learn.microsoft.com/en-us/azure/aks/app-routing-gateway-api
- https://learn.microsoft.com/en-us/azure/aks/intro-aks-automatic
