# JHUBaaS HELM CHART

This Helm chart is a customization of the one of ["Zero to Jupyter on k8s"](https://jupyterhub.github.io/helm-chart/)

## Quick start

### Requirements

- Kubernetes cluster
- Cert-Manager:
  ```
  kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.2/cert-manager.yaml
  kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.2/cert-manager.crds.yaml
  ```
- Ingress-Controller
  ```
  helm install ingress-nginx oci://ghcr.io/nginxinc/charts/nginx-ingress --create-namespace --version 1.0.2 -n ingress-nginx
  ```
- Local-path:
  ```
  kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/v0.0.24/deploy/local-path-storage.yaml
  ```
- Dask operator:
  ```
  helm install --repo https://helm.dask.org --create-namespace -n dask-operator --generate-name dask-kubernetes-operator
  ```

### Customized values

Edit the `jhub_config.py` provided in [values.yaml](values.yaml) in order to customize your JupyterHUB configuration.

### Deploy the JupyterHUB

```bash
git clone git@github.com:ICSC-Spoke2-repo/HighRateAnalysis-WP5.git
cd HighRateAnalysis-WP5/stable/jhub-aas
helm repo add jupyterhub https://jupyterhub.github.io/helm-chart/
helm dependency build
kubectl create namespace jhub
helm upgrade --install --cleanup-on-fail --namespace jhub jhub ./ 
```

## Enable offloading

Patch dask cluster custom resource:
```bash
kubectl patch crd daskclusters.kubernetes.dask.org \
  --type=json \
  -p='[
    {
      "op": "replace",
      "path": "/spec/versions/0/schema/openAPIV3Schema/properties/spec/properties/scheduler/properties/service/properties/ports/items/properties/targetPort/type",
      "value": "integer"
    }
  ]'
```

Modify `../ssh-fwd/ssh-fwd.yaml` inserting correct IP address and install ssh-forwarder machinery:
```bash
kubectl apply -f ../ssh-fwd/ssh-fwd.yaml -n jhub
kubectl apply -f ../ssh-fwd/ssh-fwd-svc.yaml -n jhub
kubectl apply -f ../ssh-fwd/listener-svc.yaml -n jhub
```

Insert kubeconfig in `../vk/kustomization/kubeconfig`
```bash
kubectl apply -k ./vk/kustomization
```

Insert the newly-created InterLink configmap name in `../vk/vk-na.yaml` and deploy the Virtual Kubelet pod (VK container + InterLink container + InterLink HTCondor Plugin container):
```bash
kubectl apply -f ../vk/vk-na.yaml -n vk
kubectl apply -f ../sa-interlink.yaml -n vk
```