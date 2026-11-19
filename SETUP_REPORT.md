# Environment Setup & Preflight Report

## 1. System & WSL2 Environment
- **OS:** Windows with WSL2 (Ubuntu 24.04.2 LTS)
- **Kernel:** Linux DESKTOP-BITKQVP 5.15.167.4-microsoft-standard-WSL2 x86_64 GNU/Linux
- **Systemd:** Enabled via `/etc/wsl.conf`
- **Resources:** 15 GB RAM, ~948 GB available disk

## 2. Installed Tool Versions
- **Docker:** 25.0.2 (build 29cf629)
- **kubectl:** Client Version v1.37.2 (Kustomize v5.8.1)
- **kind:** v0.25.0 (go1.22.9 linux/amd64)
- **Helm:** v3.22.1+gd6c1a0e
- **jq:** jq-1.7.1

## 3. Preflight Verification Results
- **Docker Test:** `docker run --rm hello-world` executed and succeeded without `sudo`.
- **Kubernetes (`kind`) Test:** Created temporary cluster `prep-check` (`kindest/node:v1.31.2`), verified `prep-check-control-plane` node reached `Ready` status via `kubectl get nodes`, and deleted the cluster cleanly.
- **Git & GitHub:** Public repository initialized at `https://github.com/yasinbayat/shipops-challenge`, authenticated via repository-scoped fine-grained PAT, initial commit pushed to `main`.
- **AI Coding Agent:** VS Code with GitHub Copilot Chat running inside `WSL: Ubuntu-24.04`. Verified file creation/inspection (`agent-check.txt`), shell execution (`uname -a`), and cleanup.
