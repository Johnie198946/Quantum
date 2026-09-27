# Hermes Bridge private Docker gateway contract

`hermes-bridge` is a host systemd service and the Compose API/workers reach it at
`http://host.docker.internal:9118`. Every caller declares
`host.docker.internal:host-gateway`; Docker maps that special value to the default
`bridge` gateway unless the daemon has an explicit host-gateway override.

The updater resolves `host.docker.internal` inside the running API container,
rejects empty, public, non-IPv4, or non-local addresses, and writes the accepted address to
`/etc/ai-lab-platform/hermes-bridge.env`. The systemd unit requires that file and
the Python bridge independently rejects anything outside RFC1918 space. The
service therefore listens only on the private Docker host address, never on
loopback, a public interface, or `0.0.0.0`. No public firewall rule for TCP 9118
is required or permitted; Ubuntu UFW may keep its normal public deny policy.
After `daemon-reload`, the installer rejects an effective systemd `ExecStart`
that bypasses the dedicated Bridge/Worker Python. `hermes_bridge.py` accepts no
command-line arguments, so `--host`, `--port`, positional, and stale drop-in
overrides fail instead of being silently ignored. The bind address comes only
from the validated environment file.

Host firewall policy still applies to container-to-host INPUT traffic. The final
API-container health probe is the authoritative check. If it fails while `ss`
shows the expected listener, permit TCP 9118 only from the Compose bridge
interface/subnet to the exact `HERMES_BRIDGE_BIND_ADDRESS`; never open the port on
a public interface or change the listener to `0.0.0.0`.

## Bridge/Worker runtime isolation

The exact-SHA updater builds a venv keyed by the runtime version and all dependency lock digests under
`/var/lib/quantumn-hermes/bridge-worker-venvs/`, owned by `quantumn-hermes`, then
atomically points `/var/lib/quantumn-hermes/bridge-worker-venv` at it. Both units
run platform code with that Python. The venv is populated from `requirements-build.lock`,
`requirements.lock`, and the host-only `requirements-bridge-worker.lock`, then the fixed
Hermes 0.21.1 source is installed with `--no-deps`. No hashed lock contains a Hermes wheel.
Startup validates that exact installed version. CLI fallback always uses
`/var/lib/quantumn-hermes/.local/bin/hermes`. Do not install platform requirements
into `.hermes/hermes-agent/venv` and do not invoke the Hermes launcher through the
Bridge/Worker venv.

After changing Docker address pools or `host-gateway-ip`, rerun the exact-SHA
updater before restarting the bridge. A resolution or local-address check failure
is a hard deployment failure; do not replace the address with `0.0.0.0`.

Verify on the host:

```bash
systemctl show hermes-bridge.service -p EnvironmentFiles
systemctl cat hermes-bridge.service
cat /etc/ai-lab-platform/hermes-bridge.env
readlink -f /var/lib/quantumn-hermes/bridge-worker-venv
sudo -u quantumn-hermes /var/lib/quantumn-hermes/bridge-worker-venv/bin/python -m pip check
sudo -u quantumn-hermes /var/lib/quantumn-hermes/bridge-worker-venv/bin/python -c \
  'import httpx, sqlalchemy, run_agent; print(run_agent.__file__)'
sudo -u quantumn-hermes /var/lib/quantumn-hermes/.hermes/hermes-agent/venv/bin/python -c \
  'import importlib.metadata; print(importlib.metadata.version("hermes-agent"))'
ss -ltnp '( sport = :9118 )'
docker compose exec -T api python -c \
  'import urllib.request; print(urllib.request.urlopen("http://host.docker.internal:9118/health", timeout=5).read().decode())'
```

The `ss` local address must equal the environment file and must be RFC1918. The
container probe must return the Hermes Bridge health JSON. A listener on
`0.0.0.0:9118`, `[::]:9118`, or `127.0.0.1:9118` fails the contract.
The printed Hermes version must be `0.21.1`; `run_agent.__file__` must be under
`/var/lib/quantumn-hermes/.hermes/hermes-agent`, while `httpx` and `sqlalchemy`
must import from the Bridge/Worker venv.

## Rollback

The updater records the prior application and Bridge/Worker venv symlink targets.
Any post-switch failure restores both before restarting services. For a manual
rollback, restore the previous immutable application release and its recorded
`bridge-worker-venv` target together, run `systemctl daemon-reload`, restart Bridge
and Worker, then repeat the version, import, listener, and container health probes.
Never point the units back at the Hermes runtime venv.

## Cloud travel / Google Maps browser

Travel research runs `browser_navigate` + `browser_snapshot` in the server's
existing Hermes runtime. It does not connect to a customer's desktop Chrome.
Use public Maps search and directions URLs; a navigation success or HTTP 200 is
not evidence that a place or transit route was read. Verify actual place/address,
route/transfer/duration and selected travel date. A route for “leave now” does
not verify a future booking. Private saved lists require a user-shared accessible
list or uploaded source, never the service account's Google login.

The September 27 server audit found working HTTP egress through the existing
loopback proxy, but no Chrome installation or required shared libraries.
Hermes 0.21.1 recognizes Playwright caches; agent-browser 0.26.0 installs Chrome
for Testing under `$HOME/.agent-browser/browsers`. The Bridge now supplies the
explicit `HERMES_HOME/browser-runtime/chrome` executable, shared read-only
browser binaries, writable socket/cache directories and `AGENT_BROWSER_PROXY`
from the service's existing HTTPS/HTTP proxy. Both Bridge and Worker use the same
composition root. User cookies and task state remain isolated by Hermes; no
personal browser profile is copied. Explicit operator browser settings win.

Provision only as part of an authorized release, before restarting either unit:

1. Ubuntu 24.04 system libraries (root; normal package-manager dependencies):

   ```sh
   apt-get install --no-install-recommends libatk1.0-0t64 libatk-bridge2.0-0t64 \
     libcups2t64 libasound2t64 libgbm1 libcairo2 libpango-1.0-0 \
     libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libatspi2.0-0t64 fonts-noto-cjk
   ```

2. Run the existing `scripts/configure_hermes_web_extract.py` as the
   `quantumn-hermes` account, using its real HOME and the existing approved
   egress environment, with `--hermes-home /var/lib/quantumn-hermes/.hermes`,
   `--plugin-source agency/hermes-plugins/ai-lab-capabilities`,
   `--backup-root /var/lib/quantumn-hermes/.hermes/backups`, and
   `--prepare-browser`. The existing Agency installer now includes that flag.
   It pins agent-browser 0.26.0, disables npm lifecycle scripts, strips provider
   credentials from child processes, verifies Chrome can load, and atomically
   links the executable. Setup failure leaves the previous executable link.
   Chrome's installer selects its stable release; record its returned version
   and executable SHA for each release. This is not a fully pinned Chrome archive.

3. Deploy through the existing exact-SHA flow. Never replace server source by
   copying the working tree. Read back the actual service environment and test
   Maps place search, dated transit routes and screenshots from that environment.
   A temporary standalone browser check is separate from production acceptance.

No Maps API credential is needed for this existing browser path. A future
structured API integration would use Places plus Routes for transit; Grounding
Lite currently covers driving/walking, so cannot replace transit verification.
Google's API caching/display terms must be reviewed before using API-derived
coordinates in the custom schematic map. That integration is not enabled here.

References: [agent-browser v0.26.0 source](https://github.com/vercel-labs/agent-browser/tree/v0.26.0)
(Apache-2.0), [Google Maps URLs](https://developers.google.com/maps/documentation/urls/get-started),
[Routes transit](https://developers.google.com/maps/documentation/routes/transit-route).
