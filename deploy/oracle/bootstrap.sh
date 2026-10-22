#!/usr/bin/env bash
# Bootstrap the LongRun Bench deployment on a fresh Oracle instance.
# Run as root ON the instance (SSH, console, or an OCI run command):
#   curl -fsSL https://raw.githubusercontent.com/darek225/longrun-bench/main/deploy/oracle/bootstrap.sh | bash -s -- <domain-or-ip>
# Clones the repo, runs install.sh, and (for a bare IP) switches Caddy
# to plain HTTP on :80 until a real domain + DNS exist.
set -euo pipefail

TARGET="${1:?usage: bootstrap.sh <domain-or-ip>}"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git curl >/dev/null

if [ ! -d /opt/longrun-bench/.git ]; then
  git clone -q https://github.com/darek225/longrun-bench.git /opt/longrun-bench
fi
cd /opt/longrun-bench
bash deploy/oracle/install.sh "${TARGET}"

# Bare IP (no dots-and-letters domain): Caddy cannot get a public cert
# for an IP, so serve plain HTTP on :80 until DNS is pointed.
if [[ "${TARGET}" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  printf ':80 {\n\treverse_proxy 127.0.0.1:8787\n\tencode gzip\n}\n' > /etc/caddy/Caddyfile
  systemctl reload caddy || systemctl restart caddy
fi

echo "Bootstrap complete: http(s)://${TARGET}/"
curl -s http://127.0.0.1:8787/api/health || true
