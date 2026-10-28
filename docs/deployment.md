# Deployment: containers, Kubernetes and GitOps

## Docker Compose

```
docker compose up --build            # http://localhost:3000, API on 127.0.0.1:8000
docker compose exec api gauntlet status
```

Both ports are published on this machine only. To open the dashboard to your network, change `127.0.0.1:3000:3000` to `3000:3000` in `docker-compose.yml`.

With no `.env`, it runs in demo mode on SQLite in a shared volume, so there are no keys or database to set up. A `migrate` service applies migrations once. Then the API, the trading floor (`worker`) and the dashboard (`web`) start, in that order, each waiting for the one before to be healthy.

Compose reads `.env` for settings, so one file serves both ways of running. There are two exceptions, because containers see the host differently:

- **Database:** `COMPOSE_DATABASE_URL` is the database as containers reach it, e.g. local Supabase at `postgresql+asyncpg://postgres:postgres@host.docker.internal:54322/postgres`. `DATABASE_URL` stays the host's view, for running without containers.
- **Supabase:** `SUPABASE_URL` and `SUPABASE_ANON_KEY` are what browsers use. The API checks sign-in tokens from inside its container through `SUPABASE_INTERNAL_URL`, e.g. `http://host.docker.internal:54321`.

Set `ADMIN_API_TOKEN` (or `ADMIN_EMAILS` with Supabase) to use the admin page.

## The images

**api** (`deploy/docker/api.Dockerfile`)
- **What it runs:** the API by default, and the trading floor with `python -m gauntlet.trading_floor`.
- **Researcher tools:** the MCP servers (fetch, Tavily, memory, Massive) are installed at their pinned versions (`mcp_tools.py`), so a run never downloads code.
- **User:** runs as a non-root user.
- **Health checks:** the API's is `/healthz`. The trading floor's is `python -m gauntlet.health`, which fails when the scheduler loop stops touching its heartbeat file.

**web** (`deploy/docker/web.Dockerfile`)
- **What it is:** the Next.js standalone server, with only `node` at runtime (the base image's npm, yarn and corepack are removed).
- **Configuration:** it reads `API_URL`, `SUPABASE_URL` and `SUPABASE_ANON_KEY` at runtime rather than at build time, so one image serves every environment.

Base images are pinned by digest; Dependabot updates them.

**On shutdown:** on SIGTERM, the trading floor stops its runs, records them as interrupted and releases its lease, so the next process takes over at once. If a process is killed outright, whichever scheduler takes the lease next marks its runs as failed.

## Kubernetes

The Helm chart in `deploy/helm/gauntlet` deploys:

| | |
|---|---|
| `web` | The dashboard, behind an Ingress. It forwards `/api/v1` to the API inside the cluster. |
| `api` | Scaled by an HPA, with a PodDisruptionBudget. Readiness checks the database. |
| `worker` | The trading floor. One replica with the `Recreate` strategy, its researchers' memory on a volume, and an exec liveness probe on the heartbeat. |
| `migrate` | A Job: an Argo CD Sync hook (after the config and secret, before the workloads), or a Helm pre-install/upgrade hook. |
| NetworkPolicies | Only `web` and `worker` can reach the API, and nothing can reach the worker. |

Pods run as non-root with read-only root filesystems, no privilege escalation and all capabilities dropped. The database stays outside the cluster, in Supabase. Secrets come from a Secret the chart doesn't create: delivered by Sealed Secrets in production, or by the bootstrap script locally.

## A local GitOps demo with k3d

Argo CD deploys what's in git, not your working copy, so first push this repository somewhere it can read. You also need Docker, [k3d](https://k3d.io), kubectl, and local Supabase running:

```
npx supabase start
deploy/scripts/cluster-up.sh           # or: make cluster-up. Then http://gauntlet.localhost:8080
deploy/scripts/cluster-down.sh
```

The script:

1. Creates a k3d cluster.
2. Builds both images and loads them into the cluster.
3. Creates the app's secret: generated keys, plus any model keys in `.env`, kept across reruns.
4. Installs Argo CD and applies `deploy/argocd/root.yaml`.

From there, Argo CD syncs everything from git: the `gauntlet` project, the Sealed Secrets controller, and the chart with `values-local.yaml`. The repository defaults to your `origin` remote at `main`; set `REPO_URL` and `REVISION` to change that.

Kubernetes 1.35 refuses to start on cgroup v1, which Docker Desktop with WSL2 may still use. In that case the script tells the kubelet to accept it.

## Production

1. Create a Supabase project and a cluster, and point kubectl at the cluster.
2. Fill in the `YOUR_*` placeholders: the host, Supabase URL and anon key in `values-prod.yaml`, and the image names in `values.yaml`.
3. Run `deploy/scripts/bootstrap-argocd.sh prod`. It installs Argo CD and the root Application, which installs the Sealed Secrets controller.
4. Seal your secrets for that controller with `deploy/scripts/seal-secrets.sh .env.prod` (needs [kubeseal](https://github.com/bitnami-labs/sealed-secrets)). Paste the output into `values-prod.yaml` and push.
   - The file needs `DATABASE_URL` (the pooler's connection string, with `postgresql+asyncpg://`) and `GAUNTLET_SECRET_KEY`, plus your model, Tavily and admin keys.
   - Only that cluster can decrypt the result.

From then on, every push to `main` runs CI, then pushes both images to GHCR tagged with the commit SHA. It then commits those tags to `values-prod.yaml`, and Argo CD rolls that commit out. So git always records what runs in production, and reverting a commit rolls it back.

- **GHCR images:** packages start private. Make them public, or add an `imagePullSecrets` entry.
- **Protected `main`:** if `main` is protected, let the workflow's bot push the tag-bump commit.
- **Rate limits:** limits on admin endpoints are counted per API replica. With the HPA at its maximum, the effective limit is that many times `ADMIN_RATE_LIMIT`.
