# ShipOps Implementation Evidence

This document records actual commands executed, verified outputs, and chronological milestones delivered during the 4-hour implementation challenge.

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
test_main.py::test_metrics_endpoint PASSED                               [100%]
======================== 4 passed, 3 warnings in 0.33s =========================
```

### 2. Local Container Verification
Commands:
```bash
docker run -d --rm --name shipops-test -p 8000:8000 -e APP_VERSION=local-test shipops-api:local
curl -s http://127.0.0.1:8000/healthz
curl -s http://127.0.0.1:8000/version
curl -s -o /dev/null -w "empty name HTTP status: %{http_code}\n" -X POST http://127.0.0.1:8000/items -H "Content-Type: application/json" -d '{"name": "   "}'
```
Verified outputs:
```text
{"status":"ok"}
{"version":"local-test"}
empty name HTTP status: 422
```
