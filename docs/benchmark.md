# Stateful AKS skills benchmark

See [the initial GPT-6.1 Sol pilot](benchmark-pilot.md) for measured results from
14 live, isolated trials.
The [help-change rerun](benchmark-help-evaluation.md) records 14 further trials
and the exact original tasks. [AKS Automatic research and scenarios](aks-automatic-scenarios.md)
describe the two additional Automatic tasks.
The [skill-content tuning experiment](skill-catalog-tuning.md) compares frozen
original and revised catalogs against the same no-skills control.

## Question and experimental unit

Does access to `az aks skill` help Copilot complete AKS tasks correctly with fewer
Azure operations, fewer model round trips, or less elapsed time?

One trial is one fresh container, one Copilot session, one task, and a fresh copy
of fake Azure state. A matched pair uses the same scenario and random seed in
two arms:

- **Baseline:** fake Azure CLI; skill commands unavailable.
- **Skills:** the same fake Azure CLI, with the repository's actual skill
  parser/renderer and a versioned catalog of general AKS procedures.

The treatment also accepts the `az aks skills` alias. Bare groups print help;
alias calls are recorded with their original argv and a normalized `aks skill`
command name so adoption counts include both spellings. Both spellings are
unavailable in the baseline. This help/alias improvement postdates the initial
pilot; historical pilot results describe the earlier interface.

All new runs use **discovery-only prompts**: the exact same task is sent in both
arms, with no mention of skills or runbooks. `--discovery passive` is the default
and only accepted value. Parent and descendant AKS help expose skill discovery
only in treatment. Historical reports retain the earlier guided-use labels;
the explicit prompt-hint mode has been removed from the runner.

The order of the two arms is seeded and shuffled per pair. Cluster/resource-group
names and capacity targets are seeded, not hardcoded in skill text. Models are
selected explicitly, never silently substituted. The default is `gpt-6.1-sol`,
verified with local Copilot CLI 1.0.98. Provider caching and backend load remain
sources of variance; fresh sessions do not disable provider-side prompt caching.

## Research-derived scenarios

These are representative documented operational workflows, not a frequency-ranked
list of the most common AKS tickets. Original sources were retrieved on November
12, 2026; Automatic sources were researched on November 13.

| Scenario | Natural task | State oracle | Source |
|---|---|---|---|
| `manual-scale` | Set a user pool to a fixed size, leaving the system pool alone | Correct count; autoscaling disabled; system pool unchanged | [Manually scale nodes](https://learn.microsoft.com/en-us/azure/aks/scale-cluster) |
| `autoscaler` | Change a pool's minimum/maximum bounds while retaining autoscaling | Correct bounds and enabled flag; system pool unchanged | [Cluster autoscaler](https://learn.microsoft.com/en-us/azure/aks/cluster-autoscaler) |
| `control-plane-upgrade` | Upgrade only the control plane | Requested supported version; all pool versions unchanged | [Upgrade the control plane](https://learn.microsoft.com/en-us/azure/aks/upgrade-aks-control-plane) |
| `stop-dev` | Stop an idle dev cluster while preserving configuration | Stopped, succeeded, same pools and configuration | [Stop/start clusters](https://learn.microsoft.com/en-us/azure/aks/start-stop-cluster) |
| `transient-scale` | Fixed-size scaling with a transient service failure | Scaling oracle plus a deterministic first-call 429 | Scaling task above; injected failure is a synthetic robustness test |
| `automatic-create` | Create Automatic with managed networking and managed system pools | Automatic/Standard SKU-tier, Auto provisioning, stable/NodeImage, correct network defaults and verification | [Automatic quickstart](https://learn.microsoft.com/en-us/azure/aks/automatic/quick-automatic-managed-network) |
| `automatic-maintenance` | Reschedule Kubernetes and node-image auto-upgrades independently | Two correct weekly windows; default window and cluster unchanged; both schedules observed | [Planned maintenance](https://learn.microsoft.com/en-us/azure/aks/planned-maintenance) |
| `debug-version-skew` | Repair a failed apps-pool upgrade | Correct control-plane/pool versions, recovered pool, unchanged system pool and counts | [Version incompatibility](https://learn.microsoft.com/en-us/troubleshoot/azure/azure-kubernetes/error-codes/nodepoolmcversionincompatible-error) |
| `debug-automatic-provider` | Repair failed Automatic creation | Required provider registered; valid Automatic cluster created and verified | [Provider registration errors](https://learn.microsoft.com/en-us/azure/azure-resource-manager/troubleshooting/error-register-resource-provider) |
| `debug-managed-namespace-quota` | Restore a stalled four-replica rollout | Approved ARM-managed quota, four ready replicas, unchanged other quotas/policies | [Managed namespaces](https://learn.microsoft.com/en-us/azure/aks/managed-namespaces) |

Important semantics captured from those sources: manual scaling conflicts with
an enabled autoscaler; `--control-plane-only` preserves pool versions; node pools
cannot upgrade ahead of the control plane; stopped clusters must start before
scale/upgrade; system pools cannot be stopped independently. Kubernetes versions
in the fixture are synthetic supported targets, not a claim about today's live
regional version availability.

The benchmark catalog is in `bench/skills/`. It contains no seeded names, task
answers, or scoring rules. The production demonstration catalog in `skills/`
remains separate from this versioned experimental input.

## Architecture and isolation

```text
host controller                         fresh container
----------------                        ----------------
scenario + hidden state + oracle         Copilot (local binary, selected model)
    ^                                         |
    | Unix socket RPC                         +--> /usr/bin/az (thin client)
mock service + authoritative trace <----------+

allowlisted HTTPS CONNECT proxy <--- Unix socket <--- loopback proxy <--- model requests
    |
    +--> Copilot auth/inference hosts OR the configured Foundry host
    X--> management.azure.com, metadata, arbitrary internet
```

The mock service lives **outside** the container. The agent cannot read expected
answers, rewrite the state, or edit the authoritative trace. It sees only the
normal task prompt, command responses and an initially empty `/work` directory.
The agent can inspect the thin client, but that client contains only the RPC
transport. This is a CLI-use experiment; direct socket requests are equivalent
mock calls and still logged and graded.

Two engines use the same services and entry point:

- **Rootless Linux namespaces (`bwrap`):** private user, PID, mount, IPC, UTS and
  network namespaces; no external interface; read-only system executables and
  client code; fresh writable home/tmp/work; all capabilities dropped. `/usr/bin/az`
  is replaced by the mock. The host's `/home`, `/opt/az`, Azure configuration,
  kubeconfig, repository, fixtures and Docker socket are not mounted.
- **Docker:** `--network none`, read-only root, no capabilities, no-new-privileges,
  nonroot UID, PID/memory/CPU limits, temporary home/work/tmp, and the same socket
  and artifact mounts. The real Azure CLI is not installed in the image.

The host proxy allows CONNECT only to exact configured HTTPS hosts on port 443,
validates their public IP addresses, and connects to the validated IP. Azure
management hosts are explicitly forbidden even if accidentally configured as
providers. The default Copilot allowlist covers api.github.com and Copilot model
hosts; telemetry destinations and arbitrary websites are blocked.
The Foundry allowlist contains only the configured inference host. Private/VNet
Foundry endpoints are not currently supported by the public-address check.

A separate logged `curl` client provides live GET-only access to approved
Microsoft Learn documentation paths and its public search endpoint. Requests
execute through a bounded host fetcher, with redirects confined to approved
paths; it cannot reach ARM. Both arms have the same docs access. `--docs-mode off`
disables it. Response bodies and hashes are retained locally for reproducibility.
This is controlled documentation access, not an unrestricted browser/search engine.
Native Copilot `web_fetch` is also supported: the container receives a public-IP
hosts mapping for learn.microsoft.com and the proxy permits that exact host.
This satisfies the tool's DNS validation before its proxied HTTPS fetch. Native
web attempts/successes/failures are counted from CLI events, separately from curl
HTTP counts; native TLS connections remain in the proxy trace. Native Learn
transport failures invalidate a trial rather than masquerading as no browsing.

Each container runs a preflight that checks external connectivity is blocked,
the proxy denies ARM, and host home/Azure CLI/credentials/fixture paths are absent.
A failing preflight stops the agent. This boundary comes from namespaces and the
proxy, not from asking the model to behave. Each run has a wall-clock timeout;
the runner kills the container process group on timeout, and removes Docker
containers explicitly. Rootless runs currently use timeout control rather than
Docker's cgroup memory/CPU limits.

Only a Copilot token or explicitly selected model-provider variables are passed
into a fresh environment. The runner does not mount personal Copilot settings,
MCP servers, plugins, shell startup scripts, previous sessions or credentials.
Built-in MCPs, automatic updates, custom instructions, remote sessions and
BASH_ENV are disabled. Copilot is told to strip model credentials from its child
tool environments. Output artifacts are local and gitignored.

## Coverage: whole command registry, focused semantic model

`bench/commands.json` captures **all 99 core `az aks` leaf commands** in the
installed Azure CLI 2.86.0 ACS module. It excludes extensions such as aks-preview
and aks-agent. `bench/capture_commands.py` refreshes this snapshot offline using
Azure CLI's own Python; it never runs a resource operation.

The simulator currently has stateful handlers for **33 core AKS commands**: cluster
list/show/create/delete/update/scale/start/stop/upgrade/version discovery/wait,
and the analogous supported nodepool operations, plus maintenanceconfiguration
list/show/add/update/delete, namespace list/show/update, get-credentials, and a
read-only kubectl simulation for command invoke (never a real remote shell).
Eight auxiliary commands have fixtures: group show/exists, provider show/list/register,
monitor activity-log list, deployment group list, and the extension's
`aks operation show-latest`. A bounded fake kubectl models context/node inspection,
deployment status, quota/events/policy inspection, combined get queries, managed
field rejection, scaling and rollout verification. Kubeconfig is written only
inside the container home or `/work`, with a nonfunctional loopback endpoint.
Handlers implement the options
needed for these workflows, not Azure's entire validation/defaulting/API contract.
For example, there is no real scheduler, VM provisioning, admission controller,
PDB drain model, auth system, quota service or regional capacity simulation.

**Every registered command can have a scripted success or failure response.**
An unimplemented command without a fixture returns `MockNotImplemented` and marks
the trial as a coverage gap; it never returns invented success and never invokes
the real Azure CLI. Unit tests exercise success/error fixtures for every command
in the registry. Run `coverage` to distinguish semantic handlers from fixture-only
commands. Add extensions explicitly to a captured registry rather than claiming
that the core snapshot includes them.

Options outside the modeled subset and unhandled non-AKS command groups also
mark a coverage gap, conservatively avoiding a model-performance penalty for a
missing simulator feature. Unknown AKS command names still receive a CLI error.

Supported output shaping: real JMESPath via pinned `jmespath==1.0.1`, JSON, TSV,
basic tables and `none`. The mock help and table layout are approximations, not
byte-for-byte Azure CLI output. Synchronous mutations complete before returning;
`--no-wait` stores a pending transition completed on later observation/wait.
All state access is serialized so concurrent tool calls cannot corrupt the
fixture. Async modeling permits one outstanding mutation at a time.

### Adding success/error fixtures

Generate a complete scenario without exposing it to the agent:

```sh
PYTHONPATH=bench .venv-bench/bin/python -c \
  'import json; from aks_bench.scenarios import make; print(json.dumps(make("manual-scale", 7), indent=2))' \
  > /tmp/opencode/scenario.json
```

Edit `faults` to inject errors on selected command occurrences. Match option keys
after alias normalization (`-g` becomes `--resource-group`):

```json
{
  "command": "aks nodepool scale",
  "occurrences": [1, 2],
  "match": {"--name": "apps"},
  "code": "TooManyRequests",
  "message": "Request throttled. Retry-After: 1 second.",
  "status": 429
}
```

Edit `responses` to define behavior for any registered command:

```json
{
  "command": "aks maintenanceconfiguration list",
  "output": [{"name": "default", "timeInWeek": []}],
  "api_requests": 1
}
```

A response may have `match`, `occurrences`, `error` (`code`, `message`, `status`),
or a replacement `clusters` array to model state changes. Unspecified occurrence
filters match every call. `faults` take precedence over successful responses.
Fixture-only commands need a `responses` entry to establish coverage before
fault injection. Unknown non-AKS commands are rejected; auxiliary `account`
inspection and version commands are local fixtures.

Run with `--fixture /tmp/opencode/scenario.json --scenarios manual-scale`.
Custom fixtures retain one of the defined scenario names/oracles. New task types
need a new oracle and prompt in `scenarios.py`, not just a successful response.

## Metrics and evidence

Each trial retains:

- `az-events.jsonl`: host-owned timestamps, argv, category, exit code, error/HTTP
  status, state hashes, modeled request count and goal status.
- `timeline.md`: readable ordered calls with relative start times and durations.
- `scenario.json`, `prompt.txt`, `final-state.json`: inputs and authoritative state.
- `agent/isolation.json`: container boundary checks.
- `copilot.stdout.jsonl`, `copilot.stderr.txt`, `agent/logs/`: agent execution evidence.
- `agent/otel.jsonl`, `agent/usage.json`: inference spans, actual observed model,
  tokens and CLI usage statistics. Prompt/response telemetry capture is disabled.
- `proxy-events.jsonl`: allowed/denied TLS tunnels, bytes and timings; no request
  bodies or authentication headers are logged by the proxy.
- `result.json`: state checks, final success, call counts, failure/coverage status.

The legacy filename `az-events.jsonl` now also holds kubectl and curl events;
the `tool` field distinguishes them. `documentation_http_requests` counts curl's actual
host-side HTTP attempts (including permitted redirects), separately from modeled
Azure and Kubernetes calls. `documents/` stores returned public documentation.
Native tool attempts are recorded in `native_web_tool_attempts`; consult both
counters before concluding that no lookup was observed. Neither count by itself
establishes that a skill saved a lookup.

The mock logs distinct quantities:

1. **CLI invocations:** all `az` calls, including local help and skill retrieval.
2. **Simulated Azure commands:** commands that would operate against Azure.
3. **Modeled API requests:** an explicit approximation: reads/errors cost one;
   state-changing synchronous mutations cost three (write + poll + final read);
   initial --no-wait requests cost one. Scripted responses may set another count.
   Skill/help/local calls cost zero. These are **not measured ARM network calls**.
4. **Model inference spans:** count/duration/token use from Copilot OTel. A logical
   inference span need not equal one physical HTTP request if the SDK retries.
5. **Proxy connections/bytes:** actual model/auth network transport, separately
   logged. TLS connection reuse means these are not an inference-request count.

Time metrics distinguish full container/agent wall time, time the state oracle
first passes, and time of the first successful relevant state read after the
oracle passes. The latter is evidence of a verification read, not proof that the
agent understood every returned field. A task passes only if the final oracle
passes, a relevant verification read occurred, and Copilot exits successfully
before timeout. Claiming success in prose does not satisfy the oracle.

`summary.json`/`summary.md` keep all failures, report success/adoption rates, and
compute paired deltas only when both matched trials succeed and have no coverage
gap. Skill adoption means a successful `show`, not merely `list` or `--help`.
Timeouts remain task failures if the harness initialized correctly. Auth/model
failures before any CLI use and coverage gaps are invalid trials, reported
separately. Do not treat faster failure as improved completion time.

`replay` runs reference sequences to validate state transitions. It is always
labeled replay and excluded from agent comparisons. It cannot establish any
benefit from skills. The benchmark does not assert that skills must win.

## Run locally

```sh
uv venv .venv-bench
uv pip install --python .venv-bench/bin/python -r bench/requirements.txt
export PYTHONPATH="$PWD/bench"

python3 -m unittest discover -s tests -v
.venv-bench/bin/python -m unittest discover -s bench/tests -v
.venv-bench/bin/python -m aks_bench coverage
.venv-bench/bin/python -m aks_bench replay --output benchmark-results/replay
```

Install Bubblewrap (`bubblewrap` package) on Linux. On this development host it
was extracted without sudo to `/tmp/opencode/bubblewrap/usr/bin/bwrap`; use that
path for `--bwrap` below. No system service or privileged installation was needed.

```sh
.venv-bench/bin/python -m aks_bench check \
  --bwrap /tmp/opencode/bubblewrap/usr/bin/bwrap \
  --output benchmark-results/isolation

.venv-bench/bin/python -m aks_bench run \
  --bwrap /tmp/opencode/bubblewrap/usr/bin/bwrap \
  --model gpt-6.1-sol --scenarios manual-scale stop-dev \
  --repeats 3 --seed 10 --timeout 180 \
  --output benchmark-results/sol-discovery
```

The runner uses `COPILOT_GITHUB_TOKEN`, `GH_TOKEN`, or `GITHUB_TOKEN` if supplied;
otherwise it obtains a token from local `gh auth token` without printing it.
Use `--gh-user USERNAME` to select another authenticated GitHub CLI account.
`--copilot /absolute/path/to/copilot` selects your installed standalone Linux
Copilot executable. This does not copy an entire personal configuration directory.
An npm JavaScript launcher needs its runtime/dependencies packaged separately;
the current container path is tested with the standalone binary.

Discovery-only is automatic; `--discovery passive` remains accepted for clarity.
Use `--skills-dir PATH` to select a catalog; it is copied into the run directory
and fingerprinted before execution. `compare --reference-skills-dir OLD_PATH`
runs baseline/original/revised conditions in interleaved seeded order.
For another model, use `--model EXACT-COPILOT-MODEL-ID`. Unsupported model IDs are
reported as failures, not replaced with another model. The same seed across model
runs gives matched scenario inputs, but models should be analyzed separately.

For Docker on a Linux host with a running daemon:

```sh
docker build -t az-aks-bench:local bench/container
.venv-bench/bin/python -m aks_bench check --engine docker \
  --output benchmark-results/docker-check
.venv-bench/bin/python -m aks_bench run --engine docker \
  --model gpt-6.1-sol --output benchmark-results/docker-sol
```

The Docker route requires host/container compatibility for the mounted local
Copilot binary and Unix sockets. The initial verified execution path is rootless
Linux namespaces; Docker was unavailable on the development host.

### Optional Foundry-backed Copilot

The installed CLI's `copilot help providers` documents Azure BYOK, including
versionless v1 and legacy versioned endpoints. GitHub's current
[custom-provider documentation](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-byok-models)
also describes `providers.json`, model/deployment mapping, streaming and tool
calling requirements. Fresh benchmark homes have no saved provider config, so
the environment-based interface is used here.

```sh
export COPILOT_PROVIDER_TYPE=azure
export COPILOT_PROVIDER_BASE_URL=https://YOUR-RESOURCE.openai.azure.com
export COPILOT_PROVIDER_API_KEY='YOUR-KEY'
export COPILOT_PROVIDER_MODEL_ID='BASE-MODEL-ID'
export COPILOT_PROVIDER_WIRE_MODEL='YOUR-DEPLOYMENT'
export COPILOT_PROVIDER_WIRE_API=responses  # use completions if required by the deployment

.venv-bench/bin/python -m aks_bench run --provider foundry \
  --model BASE-MODEL-ID --bwrap /tmp/opencode/bubblewrap/usr/bin/bwrap \
  --output benchmark-results/foundry
```

Use a full project URL if required by your endpoint, and optionally set
`COPILOT_PROVIDER_AZURE_API_VERSION`. A pre-obtained bearer token can replace the
API key via `COPILOT_PROVIDER_BEARER_TOKEN`; obtain/refresh it outside the test
container. The benchmark intentionally does not forward shell-based key-refresh
commands or Azure login credentials. Foundry execution requires a supplied
endpoint/deployment/credential; it is not exercised by the GitHub-backed pilot.

## Interpreting and extending the pilot

Start with a small smoke sweep. For an efficacy experiment, freeze code/catalog
hashes, choose scenario seeds before running, run at least 10–20 matched pairs per
scenario/model/discovery mode, and report success rates plus paired distributions
and bootstrap confidence intervals. The current report provides descriptive
medians, not statistical significance or production latency estimates.

The fixed mock delays are deliberately short. Increase `--latency-scale` for a
sensitivity run, but label it simulated latency. Real AKS operations take minutes
and can hide or amplify model/retrieval overhead; do not extrapolate pilot seconds
to Azure end-to-end deployment time. The baseline has CLI help and model knowledge
but no arbitrary web access. Compare observed controlled Microsoft Learn lookups
with skill reads; do not infer avoided browsing if the baseline never fetches docs.

Next coverage increments should be driven by observed gaps: node-image upgrades,
quota/capacity errors, add-on identity/permission failures, maintenance windows,
and read-only pod diagnostics. The current fake kubectl covers only the managed
quota rollout scenario; other Kubernetes tasks need additional state modeling. Preserve
old trials and use new output directories when changing skills or CLI affordances.
