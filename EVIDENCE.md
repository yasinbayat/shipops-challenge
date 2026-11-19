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
