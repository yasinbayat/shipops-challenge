# ShipOps Challenge — End-to-End DevOps, GitOps & Observability Pipeline

A cloud-native delivery platform running on local Kubernetes (`kind`), featuring a containerized FastAPI + PostgreSQL service, Helm packaging, automated CI/CD to GHCR, GitOps continuous delivery with Argo CD, and Prometheus observability with alerting rules.

## Prerequisites
- Docker (WSL2 / Linux), `kind`, `kubectl`, `helm`, and `git`
- Public GitHub repository with GitHub Actions & GHCR enabled

## Architecture Overview

```text
Developer Push (app/**)
        │
        ▼
GitHub Actions (.github/workflows/ci-cd.yml)
  ├─ Build python:3.12-slim Docker image & run pytest inside container
  ├─ Push immutable image tag (<short-sha>) to GHCR
  └─ Commit updated tag to charts/shipops-api/values.yaml [skip ci]
        │
        ▼
Argo CD (argocd/shipops-app.yml — automated prune & selfHeal)
  └─ Syncs Helm chart -> shipops namespace (2x FastAPI + PDB + PostgreSQL PVC)
        │
        ▼
Prometheus (monitoring/prometheus.yml — non-root, limits, probes)
  ├─ Scrapes shipops-api, argocd-application-controller, argocd-server, prometheus
  └─ Evaluates alerting rules every 10s
```

## Quickstart & Bootstrap

```bash
./scripts/bootstrap.sh
```

Verify cluster state:
```bash
kubectl get applications -n argocd
kubectl get pdb,pods,svc -n shipops
kubectl get pods,svc -n monitoring
```

## Local Access & API Examples

Forward the API service locally:
```bash
kubectl port-forward -n shipops svc/shipops-api 8081:80
```

Test endpoints:
```bash
curl -s http://localhost:8081/healthz
curl -s http://localhost:8081/readyz
curl -s http://localhost:8081/version
curl -s -X POST http://localhost:8081/items -H "Content-Type: application/json" -d '{"name":"demo-item"}'
curl -s http://localhost:8081/items/1
curl -s http://localhost:8081/metrics | head -n 20
```

### UI Access
- **Argo CD:** `kubectl port-forward -n argocd svc/argocd-server 8443:443` → `https://localhost:8443` (user: `admin`)
- **Prometheus:** `kubectl port-forward -n monitoring svc/prometheus 9090:9090` → `http://localhost:9090` (`/targets`, `/rules`, `/alerts`)

## Deployment & GitOps Rollback

- **Deploy new release:** Push changes under `app/` to `main`. GitHub Actions builds, tests, pushes `ghcr.io/yasinbayat/shipops-api:<short-sha>`, and updates `charts/shipops-api/values.yaml`. Argo CD automatically syncs the cluster.
- **Rollback via GitOps:** Revert the tag-bump commit in Git and push (do not use `kubectl set image`):
  ```bash
  git revert --no-edit <tag-bump-commit-sha>
  git push origin main
  ```

## Documentation
- **[EVIDENCE.md](./EVIDENCE.md):** Verified command outputs, CI/GHCR links, rollback proof, and chronological commit history.
- **[DECISIONS.md](./DECISIONS.md):** Engineering trade-offs, troubleshooting resolutions, and known limitations.
