#!/usr/bin/env bash
# A local GitOps demo in one command: a k3d cluster, the images built from this checkout,
# Argo CD, and Gauntlet synced from git in demo mode against local Supabase.
#
#   npx supabase start                  # first: the database
#   deploy/scripts/cluster-up.sh        # or: make cluster-up
#
# Then open http://gauntlet.localhost:8080. Needs docker, k3d and kubectl. Argo CD deploys
# what is pushed to REPO_URL (default: the origin remote) at REVISION (default: main); the
# images are always the ones built here.
set -euo pipefail

CLUSTER=${CLUSTER:-gauntlet}
HTTP_PORT=${HTTP_PORT:-8080}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
# Local Supabase on the host, as pods see it.
DATABASE_URL=${DATABASE_URL:-postgresql+asyncpg://postgres:postgres@host.k3d.internal:54322/postgres}

for tool in docker k3d kubectl; do
  command -v "$tool" >/dev/null || { echo "$tool is required" >&2; exit 1; }
done

if ! k3d cluster list "$CLUSTER" >/dev/null 2>&1; then
  echo "Creating k3d cluster $CLUSTER (dashboard on port $HTTP_PORT)"
  k3s_args=()
  if [[ "$(docker info --format '{{.CgroupVersion}}')" == "1" ]]; then
    # Kubernetes 1.35+ refuses cgroup v1 unless told otherwise; Docker Desktop on WSL2 can
    # still be on it. Fine for a local cluster (or switch WSL to cgroup v2).
    echo "Docker is on cgroup v1: allowing it in the kubelet"
    k3s_args=(--k3s-arg "--kubelet-arg=fail-cgroupv1=false@server:*;agent:*")
  fi
  k3d cluster create "$CLUSTER" --agents 1 --api-port "127.0.0.1:${API_PORT:-6550}" \
    --port "${HTTP_PORT}:80@loadbalancer" "${k3s_args[@]}" --wait
fi
kubectl config use-context "k3d-$CLUSTER" >/dev/null

echo "Building images"
docker build -f "$ROOT/deploy/docker/api.Dockerfile" -t gauntlet-api:local "$ROOT"
docker build -f "$ROOT/deploy/docker/web.Dockerfile" -t gauntlet-web:local "$ROOT"
k3d image import -c "$CLUSTER" gauntlet-api:local gauntlet-web:local

echo "Creating the gauntlet secret"
random() { od -An -tx1 -N24 /dev/urandom | tr -d ' \n'; }
# Generated keys are kept across runs, so pods that are already running stay consistent.
existing() { kubectl -n gauntlet get secret gauntlet -o jsonpath="{.data.$1}" 2>/dev/null | base64 -d || true; }
secret_key=$(existing GAUNTLET_SECRET_KEY)
admin_token=$(existing ADMIN_API_TOKEN)
secret_args=(
  --from-literal=DATABASE_URL="$DATABASE_URL"
  --from-literal=GAUNTLET_SECRET_KEY="${secret_key:-$(random)}"
  --from-literal=ADMIN_API_TOKEN="${admin_token:=$(random)}"
)
# Model and tool keys from .env, if any (demo mode needs none).
if [[ -f "$ROOT/.env" ]]; then
  while IFS='=' read -r key value; do
    [[ -n "$value" ]] && secret_args+=(--from-literal="$key=$value")
  done < <(grep -E '^(OPENAI|ANTHROPIC|GOOGLE|DEEPSEEK|GROK|OPENROUTER|TAVILY|MASSIVE)_API_KEY=' "$ROOT/.env" || true)
fi
kubectl create namespace gauntlet --dry-run=client -o yaml | kubectl apply -f -
kubectl -n gauntlet create secret generic gauntlet "${secret_args[@]}" --dry-run=client -o yaml | kubectl apply -f -

"$ROOT/deploy/scripts/bootstrap-argocd.sh" local

echo
echo "Gauntlet: http://gauntlet.localhost:$HTTP_PORT"
echo "Admin:     sign in as admin@gauntlet.local, or with the token $admin_token"
