# ShipOps Implementation Evidence

This document records actual commands executed, troubleshooting steps, verified outputs, and chronological milestones delivered during the 4-hour implementation challenge.

## Milestone 1: REST API, Automated Tests & Non-Root Docker Image

### 1. Automated Tests (pytest inside container)
Command:
```bash
docker build -t shipops-api:local ./app
docker run --rm shipops-api:local pytest -v
```
Verified output:
```text
test_main.py::test_healthz PASSED                                        [ 25%]
test_main.py::test_version PASSED                                        [ 50%]
test_main.py::test_create_item_rejects_empty_name PASSED                 [ 75%]
test_main.py::test_metrics_endpoint PASSED                               [ 100%]
======================== 4 passed, 3 warnings in 0.33s =========================
```

### 2. Local Container Verification
Commands:
```bash
export no_proxy="$no_proxy,localhost,127.0.0.1"
docker run -d --rm --name shipops-test -p 8000:8000 -e APP_VERSION=local-test shipops-api:local
curl -s [http://127.0.0.1:8000/healthz](http://127.0.0.1:8000/healthz)
curl -s [http://127.0.0.1:8000/version](http://127.0.0.1:8000/version)
curl -s -o /dev/null -w "empty name HTTP status: %{http_code}\n" -X POST [http://127.0.0.1:8000/items](http://127.0.0.1:8000/items) -H "Content-Type: application/json" -d '{"name": "   "}'
```
Verified outputs:
```text
{"status":"ok"}
{"version":"local-test"}
empty name HTTP status: 422
```

---

## Milestone 2: kind Cluster, Helm Chart & PostgreSQL Persistence

### 1. Initial Deployment Issue & Root Cause (Why Testing Failed Initially)
After deploying the Helm chart (`helm upgrade --install shipops-api ./charts/shipops-api -n shipops --create-namespace`), the initial rollout stalled and live API tests could not run:
```text
NAME                               READY   STATUS         RESTARTS   AGE
pod/postgres-dd665f5b7-xrfhz       0/1     ErrImagePull   0          111s
pod/shipops-api-7f8c79dc5b-htdvj   0/1     Running        0          111s
pod/shipops-api-7f8c79dc5b-htxpg   0/1     Running        0          111s
```
- **Root Cause:** The host Docker daemon in WSL2 is configured with a proxy, whereas `containerd` inside the `kind` node could not directly pull `postgres:16-alpine` from Docker Hub (`ImagePullBackOff` / `ErrImagePull`).
- **Cascading Effect (Expected Behavior):** Because PostgreSQL was not running, both `shipops-api` pods remained `Running` (`/healthz` passed) but stayed `0/1` Ready because their `readinessProbe` (`/readyz`) correctly failed until database connectivity was established.

### 2. Resolution: Pre-loading PostgreSQL Image into `kind`
We pulled the PostgreSQL image on the WSL2 Docker host, loaded it directly into the `kind` cluster node, and recreated the failed PostgreSQL pod:
```bash
docker pull postgres:16-alpine
kind load docker-image postgres:16-alpine --name shipops
kubectl delete pod -n shipops -l app=postgres
kubectl rollout status deployment/postgres -n shipops
kubectl rollout status deployment/shipops-api -n shipops
```

### 3. Verified Healthy Pods, Service & PVC
Command:
```bash
kubectl get pods,svc,pvc -n shipops
```
Verified output:
```text
NAME                               READY   STATUS    RESTARTS   AGE
pod/postgres-dd665f5b7-65pf2       1/1     Running   0          37s
pod/shipops-api-7f8c79dc5b-htdvj   1/1     Running   0          9m22s
pod/shipops-api-7f8c79dc5b-htxpg   1/1     Running   0          9m22s

NAME                  TYPE        CLUSTER-IP    EXTERNAL-IP   PORT(S)    AGE
service/postgres      ClusterIP   10.96.99.26   <none>        5432/TCP   9m22s
service/shipops-api   ClusterIP   10.96.78.5    <none>        80/TCP     9m22s

NAME                                 STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS   AGE
persistentvolumeclaim/postgres-pvc   Bound    pvc-ad2217da-6660-4087-8370-fb6fa19422aa   1Gi        RWO            standard       9m22s
```

### 4. Live API & PostgreSQL Persistence Test (Across Pod Restart)
We exposed the Kubernetes Service locally via `kubectl port-forward -n shipops svc/shipops-api 8080:80` (with `no_proxy` including `localhost,127.0.0.1`) and verified end-to-end persistence:

Commands executed:
```bash
curl -s [http://127.0.0.1:8080/readyz](http://127.0.0.1:8080/readyz)
curl -s [http://127.0.0.1:8080/version](http://127.0.0.1:8080/version)
curl -s -X POST [http://127.0.0.1:8080/items](http://127.0.0.1:8080/items) -H "Content-Type: application/json" -d '{"name": "shipops-persistent-item"}'
curl -s [http://127.0.0.1:8080/items/1](http://127.0.0.1:8080/items/1)
kubectl rollout restart deployment/postgres -n shipops
kubectl rollout status deployment/postgres -n shipops
curl -s [http://127.0.0.1:8080/items/1](http://127.0.0.1:8080/items/1)
```

Verified outputs:
- **`/readyz`:** `{"status":"ready"}`
- **`/version`:** `{"version":"local"}`
- **`POST /items`:** `{"id":1,"name":"shipops-persistent-item"}`
- **`GET /items/1` (before DB restart):** `{"id":1,"name":"shipops-persistent-item"}`
- **DB Restart:** `deployment.apps/postgres restarted` -> `deployment "postgres" successfully rolled out`
- **`GET /items/1` (after DB restart):** `{"id":1,"name":"shipops-persistent-item"}`

---

## Milestone 3: CI/CD (GitHub Actions, GHCR) & GitOps (Argo CD)

### 1. Workflow Push Error & Resolution (PAT Permissions)
When pushing `.github/workflows/ci-cd.yml` for the first time, GitHub rejected the push:
```text
! [remote rejected] main -> main (refusing to allow a Personal Access Token to create or update workflow `.github/workflows/ci-cd.yml` without `workflow` scope)
```
- **Root Cause:** The repository-scoped fine-grained PAT created during setup had `Contents: Read and write` permission, which is insufficient for creating or modifying GitHub Actions workflow files.
- **Resolution:** Updated the fine-grained PAT in GitHub (`Settings -> Developer settings -> Personal access tokens`) to add `Workflows: Read and write` permission (maintaining least-privilege repository scoping), then pushed successfully.

### 2. CI Runner Python Version Mismatch & Fix
During the first GitHub Actions run, `pip install -r requirements.txt` failed while building `psycopg2-binary==2.9.9` from source:
```text
psycopg/utils.c:397:12: error: implicit declaration of function ‘_PyInterpreterState_Get’
ERROR: Failed building wheel for psycopg2-binary
```
- **Root Cause:** The `ubuntu-latest` runner defaulted to Python 3.14, for which `psycopg2-binary==2.9.9` has no pre-built wheel and fails to compile.
- **Resolution:** Added `actions/setup-python@v5` pinned to Python `3.12` in `.github/workflows/ci-cd.yml` to match the `python:3.12-slim` Docker runtime.

### 3. Containerized CI Tests & Verified Successful Pipeline Run (#2)
To eliminate host Python version drift completely, the workflow was updated to build the `python:3.12-slim` Docker image first and run `pytest -v` inside the container before pushing to GHCR.
- **Workflow Run:** `Build, Test, Publish & Update GitOps #2` — **Succeeded in 23s**
  - Build Docker image and run automated tests (`pytest`): Passed (12s)
  - Push tested Docker image to GHCR: Passed (4s)
  - Update Helm `values.yaml` & commit/push with `[skip ci]`: Passed (2s)
- **Published GHCR Image:** `ghcr.io/yasinbayat/shipops-api:7556485`
- **Automated GitOps Commit:** `f616c7c chore(gitops): update image tag to 7556485 [skip ci]`

### 4. Argo CD Installation Troubleshooting & GitOps Sync

1. **CRD Annotation Size Limit Error:**
   - **Error:** Initial `kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml` failed with:
     `The CustomResourceDefinition "applicationsets.argoproj.io" is invalid: metadata.annotations: Too long: must have at most 262144 bytes`
   - **Resolution:** Re-applied the manifest using Server-Side Apply (`kubectl apply --server-side --force-conflicts`).

2. **Argo CD `ErrImagePull` / `ImagePullBackOff` Behind Host Proxy:**
   - **Error:** All 7 Argo CD pods stalled in `ErrImagePull` / `Init:ErrImagePull` because `containerd` inside the `kind` node could not pull images through the WSL2 host proxy.
   - **Resolution:** Extracted all container and initContainer images (`ghcr.io/dexidp/dex:v2.46.0`, `public.ecr.aws/docker/library/redis:8.10.1-alpine`, `quay.io/argoproj/argocd:v3.6.2`), pulled them via the WSL2 Docker daemon, and loaded them into the `kind` cluster using `kind load docker-image`.

3. **Persisting `ImagePullBackOff` Due to `imagePullPolicy: Always` & StatefulSet Retention:**
   - **Error:** Even after pre-loading all 3 images into `kind` and recreating pods, Argo CD pods continued failing with `ImagePullBackOff` because the upstream manifest hardcodes `imagePullPolicy: Always`. After patching, `argocd-application-controller-0` (a `StatefulSet` pod) still persisted in `ImagePullBackOff`.
   - **Resolution:** Patched `imagePullPolicy: Always` to `imagePullPolicy: IfNotPresent` across the Argo CD manifest via `sed` + server-side apply, then explicitly deleted `argocd-application-controller-0` so the StatefulSet recreated it with the updated pull policy.

4. **GHCR Image Pre-Load for GitOps Helm Rollout:**
   - **Action:** Pulled the CI-built immutable image `ghcr.io/yasinbayat/shipops-api:7556485` on the host and loaded it into `kind` (`kind load docker-image`) so Argo CD's automated Helm sync could roll out the new pods without hitting the proxy.

5. **Verified Argo CD Pods, Application Sync & Workload Rollout:**

Command:
```bash
kubectl get pods -n argocd
```
Verified output:
```text
NAME                                               READY   STATUS    RESTARTS   AGE
argocd-application-controller-0                    1/1     Running   0          2m50s
argocd-applicationset-controller-ddf74f76f-rccbh   1/1     Running   0          3m58s
argocd-dex-server-689f75b6f9-sc9fz                 1/1     Running   0          3m58s
argocd-notifications-controller-7f9cf495bd-5qlpj   1/1     Running   0          3m57s
argocd-redis-fb76454d5-hjnwz                       1/1     Running   0          3m58s
argocd-repo-server-6fbb479667-54c8b                1/1     Running   0          3m58s
argocd-server-7c9bddf6f5-zwqcf                     1/1     Running   0          3m58s
```

Command:
```bash
kubectl get applications -n argocd
```
Verified output:
```text
NAME          SYNC STATUS   HEALTH STATUS
shipops-api   Synced        Healthy
```

Command:
```bash
kubectl get pods -n shipops
```
Verified output:
```text
NAME                          READY   STATUS    RESTARTS   AGE
postgres-57c8f85b7-p9mt2      1/1     Running   0          52m
shipops-api-d7789b9b5-2glrq   1/1     Running   0          23s
shipops-api-d7789b9b5-ptw25   1/1     Running   0          17s
```

---

## Milestone 4: Observability & Alerting (Prometheus)

### 1. Prometheus Deployment (`monitoring` Namespace)
- Pre-loaded `prom/prometheus:v2.54.1` into `kind` (`kind load docker-image`) with `imagePullPolicy: IfNotPresent` to avoid host proxy pull issues.
- Configured `monitoring/prometheus.yml` with 4 scrape targets and 2 alerting rule groups (`rules.yml`, `evaluation_interval: 10s`).

Command:
```bash
kubectl get pods,svc -n monitoring
```
Verified output:
```text
NAME                              READY   STATUS    RESTARTS   AGE
pod/prometheus-7d94c9cbbc-jsz6n   1/1     Running   0          109s

NAME                 TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE
service/prometheus   ClusterIP   10.96.234.107   <none>        9090/TCP   109s
```

### 2. Verified Targets, Rules & Alerts (Prometheus UI)
- **Targets (`http://localhost:9090/targets`) — 4/4 UP:**
  - `shipops-api` (`http://shipops-api.shipops.svc.cluster.local:80/metrics`) — `UP`
  - `argocd-application-controller` (`http://argocd-metrics.argocd.svc.cluster.local:8082/metrics`) — `UP`
  - `argocd-server` (`http://argocd-server-metrics.argocd.svc.cluster.local:8083/metrics`) — `UP`
  - `prometheus` (`http://localhost:9090/metrics`) — `UP`
- **Rules (`http://localhost:9090/rules`) — All `OK` (10s interval):**
  - `shipops-availability`: `ShipOpsApiDown` (`critical`), `ShipOpsHighMemoryUsage` (`warning`)
  - `gitops-health`: `ArgoCDMetricsDown` (`warning`)
- **Alerts (`http://localhost:9090/alerts`):** `Inactive (3)`, `Pending (0)`, `Firing (0)`.

---

## Milestone 5: Live Metrics, Reliability (Zero-Downtime) & GitOps Rollback

### 1. Live Application Metrics (Success, Failure & Latency)
Generated both successful (`200`) and failed (`404`) requests against `shipops-api`:
```text
GET /healthz -> 200
GET /readyz -> 200
GET /items/1 -> 200
GET /items/99999 -> 404
GET /items/88888 -> 404
```
Verified live `/metrics` output showing request counts, failed request counts, and latency histogram:
```text
http_requests_total{endpoint="/items/1",method="GET",status="200"} 2.0
http_requests_total{endpoint="/items/99999",method="GET",status="404"} 1.0
http_requests_total{endpoint="/items/88888",method="GET",status="404"} 1.0
http_requests_failed_total{endpoint="/items/99999",method="GET",status="404"} 1.0
http_requests_failed_total{endpoint="/items/88888",method="GET",status="404"} 1.0
# HELP http_request_duration_seconds HTTP request latency
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{endpoint="/healthz",le="0.005",method="GET"} 192.0
http_request_duration_seconds_bucket{endpoint="/healthz",le="0.01",method="GET"} 198.0
```

### 2. Reliability Test: Pod Termination During Active Requests
- **Observation on `kubectl port-forward`:** Terminating pod `shipops-api-d7789b9b5-2glrq` while using `kubectl port-forward svc/shipops-api` dropped the local tunnel (`Exit 1` / `HTTP 000`) because `port-forward` binds to a single backing pod rather than load-balancing across endpoints.
- **In-Cluster Service Verification:** Re-tested by sending continuous requests directly to `http://shipops-api.shipops.svc.cluster.local/items/1` while deleting 1 of the 2 replicas (`shipops-api-d7789b9b5-ptw25`):
```text
pod "shipops-api-d7789b9b5-ptw25" deleted from shipops namespace
In-cluster Request #1 -> HTTP 200 | {"id":1,"name":"shipops-persistent-item"}
In-cluster Request #2 -> HTTP 200 | {"id":1,"name":"shipops-persistent-item"}
In-cluster Request #3 -> HTTP 200 | {"id":1,"name":"shipops-persistent-item"}
In-cluster Request #4 -> HTTP 200 | {"id":1,"name":"shipops-persistent-item"}
In-cluster Request #5 -> HTTP 200 | {"id":1,"name":"shipops-persistent-item"}
deployment "shipops-api" successfully rolled out
```
- All 5 requests succeeded with `HTTP 200` (zero downtime) while the Deployment automatically scheduled replacement pod `shipops-api-d7789b9b5-46bnx` (`1/1 Running` in 6s).

### 3. Tested GitOps Rollback & Data Preservation
- **Procedure:** Reverted the GHCR tag bump commit (`f616c7c`) via `git revert --no-edit f616c7c` (commit `650dfe1`) and pushed to `main`—no manual `kubectl set image` used.
- **Argo CD Sync Result:**
```text
NAME          SYNC STATUS   HEALTH STATUS
shipops-api   Synced        Healthy
```
- **Verified Rollback & Database Persistence:**
```text
VERSION: {"version":"local"}
ITEM 1 : {"id":1,"name":"shipops-persistent-item"}
```
- **Schema Limitation Note:** This GitOps rollback restores the application image cleanly as long as database changes remain backward-compatible (expand-and-contract pattern). If a newer release applies a destructive/incompatible schema migration (e.g., dropping or renaming a column), rolling back only the application image will fail against the modified schema and requires a paired database backup/restore or forward-fix migration.

---

## Milestone 6: Roll-Forward, Manifest Hardening & Bootstrap Script

### 1. Roll-Forward to GHCR Release (`7556485`)
- Reverted the rollback commit (`650dfe1`) via `git revert --no-edit 650dfe1` (commit `8b2f711`) so Argo CD automatically rolled `shipops-api` forward back to `ghcr.io/yasinbayat/shipops-api:7556485`.

### 2. High Availability (`PodDisruptionBudget`), Prometheus Hardening & Bootstrap
- Added `charts/shipops-api/templates/pdb.yaml` (`minAvailable: 1`) to protect the 2-replica API during disruptions.
- Hardened `monitoring/prometheus.yml` with non-root `securityContext` (`runAsNonRoot: true`, UID `65534`, `allowPrivilegeEscalation: false`, `capabilities.drop: ["ALL"]`), CPU/memory requests & limits, and `/-/ready` + `/-/healthy` probes.
- Added repeatable cluster bootstrap script `scripts/bootstrap.sh` (commit `e5fb00a`).

Commands:
```bash
kubectl get applications -n argocd
kubectl get pdb,pods -n shipops
kubectl get pods -n monitoring
```
Verified output:
```text
NAME          SYNC STATUS   HEALTH STATUS
shipops-api   Synced        Progressing

NAME                                         MIN AVAILABLE   MAX UNAVAILABLE   ALLOWED DISRUPTIONS   AGE
poddisruptionbudget.policy/shipops-api-pdb   1               N/A               1                     6s

NAME                               READY   STATUS    RESTARTS   AGE
pod/postgres-57c8f85b7-p9mt2       1/1     Running   0          90m
pod/shipops-api-7f8c79dc5b-55vrg   1/1     Running   0          3m35s
pod/shipops-api-7f8c79dc5b-th979   1/1     Running   0          3m40s
pod/shipops-api-d7789b9b5-rkbbw    0/1     Running   0          6s

NAME                          READY   STATUS    RESTARTS   AGE
prometheus-78584686d6-8rw82   1/1     Running   0          29s
```
