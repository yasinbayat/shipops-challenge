# Engineering Decisions, Trade-offs & Limitations

## Key Architectural Choices
- **FastAPI + PostgreSQL + `prometheus_client`:** Lightweight Python stack with native async support, OpenAPI docs (`/docs`), and `/metrics` instrumentation (`http_requests_total`, `http_requests_failed_total`, `http_request_duration_seconds`).
- **Containerized CI Tests:** Moved `pytest` execution inside the built `python:3.12-slim` Docker image in GitHub Actions rather than the runner's host Python environment to eliminate version drift (GitHub's Ubuntu runner defaulted to Python 3.14, causing dependency build failures).
- **Immutable Image Tags & Loop Prevention:** Published images to GHCR tagged with the short Git commit SHA (never `latest`) and appended `[skip ci]` to the automated `charts/shipops-api/values.yaml` commit to prevent infinite CI loops.
- **GitOps Rollback (`git revert`):** Used `git revert` on the desired-state tag commit rather than imperative `kubectl set image` so Git remains the single source of truth for Argo CD.

## Real-World Failures & Fixes
1. **GitHub Actions PAT Scope:** Initial workflow push failed until the token had `workflow` scope.
2. **Argo CD CRD Size Limit:** Upstream `install.yaml` exceeded client-side `last-applied-configuration` annotation limits (`> 262144 bytes`); resolved with `kubectl apply --server-side --force-conflicts`.
3. **Host Proxy & `kind` Image Pulls:** `containerd` inside the `kind` node could not pull images through the WSL2 proxy. Resolved by pre-loading images via `docker pull` + `kind load docker-image`, patching Argo CD's `imagePullPolicy: Always` to `IfNotPresent`, and recreating the StatefulSet pod `argocd-application-controller-0`.
4. **`kubectl port-forward` vs. In-Cluster Service Routing:** Deleting a pod during `port-forward` dropped the local tunnel because `port-forward` binds to a single pod. Verified true zero-downtime Service load-balancing by sending requests directly to `shipops-api.shipops.svc.cluster.local` during pod termination.

## AI Agent Usage (Accepted vs. Adjusted)
- **Accepted:** Helm chart scaffolding, Prometheus alerting rules (`ShipOpsApiDown`, `ShipOpsHighMemoryUsage`, `ArgoCDMetricsDown`), `PodDisruptionBudget`, and non-root Prometheus hardening.
- **Adjusted / Rejected:** Rejected relying on host-side `pytest` in CI after observing the Python 3.14 failure; rejected `kubectl port-forward` as a zero-downtime proof and switched to in-cluster Service testing; expanded Prometheus beyond a single API target to also monitor Argo CD metrics.

## Known Limitations
- **Database Schema Rollbacks:** GitOps `git revert` safely rolls back application code only if database migrations are backward-compatible (expand-and-contract). Destructive schema changes require a paired DB restore or forward-fix migration.
- **Local `kind` Proxy Environment:** New GHCR images built in CI must be pre-loaded into `kind` (`kind load docker-image`) when running behind the local WSL2 proxy.
- **Single-Node `kind` Cluster:** `PodDisruptionBudget` and `2` replicas protect against pod termination and rolling updates, but not full host/cluster loss.
