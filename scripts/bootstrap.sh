#!/usr/bin/env bash
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-shipops}"

echo "=== 1. Creating kind cluster (${CLUSTER_NAME}) if not present ==="
if ! kind get clusters | grep -qx "${CLUSTER_NAME}"; then
  kind create cluster --name "${CLUSTER_NAME}"
fi

echo "=== 2. Installing Argo CD (server-side apply) ==="
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
curl -sL https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml \
  | sed 's/imagePullPolicy: Always/imagePullPolicy: IfNotPresent/g' \
  | kubectl apply --server-side --force-conflicts -n argocd -f -

echo "=== 3. Applying Argo CD GitOps Application ==="
kubectl apply -f argocd/shipops-app.yml

echo "=== 4. Deploying Prometheus monitoring stack ==="
kubectl apply -f monitoring/prometheus.yml

echo "=== Bootstrap complete. Check status with: ==="
echo "  kubectl get applications -n argocd"
echo "  kubectl get pods -n shipops"
echo "  kubectl get pods -n monitoring"
