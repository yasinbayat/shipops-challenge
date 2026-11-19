# ShipOps Challenge — End-to-End DevOps, GitOps & Observability Pipeline

A complete cloud-native delivery workflow running on a local `kind` Kubernetes cluster, featuring a containerized FastAPI + PostgreSQL service, Helm packaging, automated CI/CD to GHCR, GitOps continuous delivery with Argo CD, and Prometheus monitoring with alerting rules.

## Architecture Overview

```text
Developer Push (app/**)
        │
        ▼
GitHub Actions (.github/workflows/ci-cd.yml)
  ├─ Build python:3.12-slim Docker image
  ├─ Run pytest inside container (eliminates host Python drift)
  ├─ Push immutable image tag (<short-sha>) to GHCR
  └─ Commit updated tag to charts/shipops-api/values.yaml [skip ci]
        │
        ▼
Argo CD (argocd/shipops-app.yml — prune & selfHeal enabled)
  └─ Syncs Helm chart -> shipops namespace (FastAPI + PostgreSQL)
        │
        ▼
Prometheus (monitoring/prometheus.yml)
  ├─ Scrapes shipops-api, argocd-application-controller, argocd-server, prometheus
  └─ Evaluates alerting rules every 10s (availability & GitOps health)
```

## Repository Structure

```text
.
├── .github/workflows/ci-cd.yml   # Containerized pytest, GHCR publish & GitOps tag bump
├── app/                          # FastAPI service, Dockerfile (python:3.12-slim), pytest suite
├── charts/shipops-api/           # Helm chart for shipops-api and PostgreSQL
├── argocd/shipops-app.yml        # Argo CD Application manifest (automated sync)
├── monitoring/prometheus.yml     # Prometheus ConfigMap, Alerting Rules, Deployment & Service
├── EVIDENCE.md                   # Verified command outputs & troubleshooting log (Milestones 1–4)
└── README.md
```

## Quickstart & Local Access

### 1. Deploy / Verify Workloads
```bash
kubectl get pods -n shipops
kubectl get applications -n argocd
kubectl get pods,svc -n monitoring
```

### 2. Access Services Locally (Port-Forwarding)
- **ShipOps API:**
  ```bash
  kubectl port-forward -n shipops svc/shipops-api 8081:80
  ```
  - Health / Version: `http://localhost:8081/version`
  - Swagger Docs: `http://localhost:8081/docs`
  - Metrics: `http://localhost:8081/metrics`

- **Argo CD UI:**
  ```bash
  kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d; echo
  kubectl port-forward -n argocd svc/argocd-server 8443:443
  ```
  - URL: `https://localhost:8443` (Username: `admin`)

- **Prometheus UI:**
  ```bash
  kubectl port-forward -n monitoring svc/prometheus 9090:9090
  ```
  - Targets: `http://localhost:9090/targets`
  - Rules: `http://localhost:9090/rules`
  - Alerts: `http://localhost:9090/alerts`

## Evidence & Troubleshooting Log

All verified outputs, CI run results, and real-world debugging resolutions (PAT workflow scope, runner Python 3.14 mismatch, Argo CD CRD server-side apply, `kind` proxy image pre-loading, and `imagePullPolicy` overrides) are documented in **[EVIDENCE.md](./EVIDENCE.md)**.
