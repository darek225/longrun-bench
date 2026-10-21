#!/usr/bin/env bash
# LongRun Bench production install for an Oracle Cloud Always Free
# Ampere A1 instance (Ubuntu 24.04 ARM). Run as root on the instance.
# Prereqs: the instance's security list allows inbound 80/443 (and 22
# for SSH); a DNS A record for the domain points at the instance.
set -euo pipefail

DOMAIN="${1:?usage: install.sh <domain>}"

apt-get update
apt-get install -y python3 git curl debian-keyring debian-archive-keyring apt-transport-https

# Caddy (official apt repo) for automatic HTTPS.
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
apt-get update && apt-get install -y caddy

id longrun >/dev/null 2>&1 || useradd --system --home /opt/longrun-bench --shell /usr/sbin/nologin longrun
mkdir -p /opt/longrun-bench
if [ ! -d /opt/longrun-bench/.git ]; then
  git clone https://github.com/darek225/longrun-bench.git /opt/longrun-bench.tmp
  cp -a /opt/longrun-bench.tmp/. /opt/longrun-bench/
  rm -rf /opt/longrun-bench.tmp
fi
cd /opt/longrun-bench

# Production secrets live here (Google OAuth client id/secret). Create
# once; never commit this file.
[ -f .env.production ] || { touch .env.production; chmod 600 .env.production; }

cp deploy/oracle/longrun-leaderboard.service /etc/systemd/system/
cp deploy/oracle/longrun-backup.service /etc/systemd/system/
cp deploy/oracle/longrun-backup.timer /etc/systemd/system/
sed "s/YOUR_DOMAIN/${DOMAIN}/" deploy/oracle/Caddyfile > /etc/caddy/Caddyfile

chown -R longrun:longrun /opt/longrun-bench
systemctl daemon-reload
systemctl enable --now longrun-leaderboard.service
systemctl enable --now longrun-backup.timer
systemctl reload caddy || systemctl restart caddy

echo "Installed. Health: curl -s http://127.0.0.1:8787/api/health"
echo "Public:   https://${DOMAIN}/ (board), https://${DOMAIN}/agent (agent link)"
