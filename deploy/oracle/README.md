# Oracle deployment

Production target: Oracle Cloud Always Free, one Ampere A1 instance
(2 OCPU / 12 GB, Ubuntu 24.04 ARM). Always Free, no expiry. The whole
site is one Python process plus a SQLite file, so this is oversized on
purpose.

## Darek's part (account + instance, about 10 minutes)

1. Sign up at cloud.oracle.com (card is for identity verification; the
   Always Free resources are never charged). Pick home region
   **US East (Ashburn)**: closest to NC with the best A1 capacity. The
   home region cannot be changed later.
2. Create an instance: Compute -> Instances -> Create. Name
   `longrun-bench`. Image: Ubuntu 24.04 (aarch64). Shape: Ampere A1
   Flex, 2 OCPU / 12 GB, and confirm it says **Always Free eligible**.
   Boot volume: 50 GB is enough (200 GB total allowance).
3. Networking: default VCN is fine. Under "Security lists", make sure
   inbound rules allow TCP 80 and 443 from 0.0.0.0/0 (22 for SSH is
   there by default).
4. SSH keys: choose "Paste public keys" and paste the key Muse gives
   you in chat for this deployment.
5. Create, then tell Muse the instance's public IP.

## Muse's part (everything after)

SSH in, clone this repo, run `deploy/oracle/install.sh <domain>`:
installs Python + Caddy (automatic HTTPS), creates the `longrun`
service user, installs the systemd units, starts the board, and arms
the daily DB backup timer (backups go to the private
`darek225/longrun-bench-data` repo). Then:

- Point the domain's DNS A record at the instance (or run pre-domain on
  the IP with a temporary hostname).
- Add the Google OAuth redirect URI
  (`https://<domain>/api/auth/google/callback`) to the OAuth client and
  put the client ID/secret in `/opt/longrun-bench/.env.production`
  (never in the repo).
- Create Darek's account on the live site, verify: public board loads
  logged-out, `/agent` serves the agent instructions, one upload with
  his token lands a row with his name as submitter.

## Notes

- Oracle can reclaim instances idle below 20% utilization for 7 days.
  A public site plus the daily backup timer keeps this instance
  visibly active; if traffic is ever truly zero for a week, a trivial
  keepalive cron (health ping every few minutes) covers it.
- Updates: `git pull` in /opt/longrun-bench + `systemctl restart
  longrun-leaderboard`. The DB file is untouched by deploys.
