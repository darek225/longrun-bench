# Vercel front door (interim public face)

Static copy of `leaderboard/site/index.html` deployed to a free
`*.vercel.app` subdomain so the public URL is a clean name with
automatic HTTPS, while the Oracle instance stays the backend.

`vercel.json` rewrites proxy `/api/*`, `/agent*`, and `/llms.txt`
server-side to the Oracle instance, so the browser only ever talks
to the Vercel origin (no mixed content, session cookies first-party
to the public URL).

If the instance IP changes, update the destinations in
`vercel.json` and redeploy (`npx vercel --prod` from this folder).

This is an interim face until longrunbench.com is registered; then
DNS points at the instance, Caddy terminates TLS itself, and this
front door can be retired.
