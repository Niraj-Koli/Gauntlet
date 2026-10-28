#!/usr/bin/env bash
# Install Argo CD in the current kubectl context and point it at this repository. From
# then on the cluster follows git: the root Application syncs deploy/argocd/apps, which
# deploys the Sealed Secrets controller and the Gauntlet chart.
#
#   deploy/scripts/bootstrap-argocd.sh [local|prod]
#
# REPO_URL (default: this checkout's origin remote) and REVISION (default: main) choose what
# Argo CD follows. The repository must be one Argo CD can read: public, or added with
# `argocd repo add` first.
set -euo pipefail

ENV_NAME=${1:-local}
ARGOCD_VERSION=${ARGOCD_VERSION:-v3.5.4}
REVISION=${REVISION:-main}
REPO_URL=${REPO_URL:-$(git -C "$(dirname "$0")" remote get-url origin 2>/dev/null || true)}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)

if [[ -z "$REPO_URL" ]]; then
  echo "Set REPO_URL to the git repository Argo CD should follow (there is no origin remote)." >&2
  exit 1
fi
case "$ENV_NAME" in local | prod) ;; *) echo "Environment must be local or prod" >&2; exit 1 ;; esac

echo "Installing Argo CD $ARGOCD_VERSION"
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
kubectl apply --server-side --force-conflicts -n argocd \
  -f "https://raw.githubusercontent.com/argoproj/argo-cd/${ARGOCD_VERSION}/manifests/install.yaml"
kubectl -n argocd rollout status deployment/argocd-server --timeout=5m
kubectl -n argocd rollout status deployment/argocd-repo-server --timeout=5m
kubectl -n argocd rollout status statefulset/argocd-application-controller --timeout=5m

echo "Following $REPO_URL at $REVISION ($ENV_NAME)"
sed -e "s|\${REPO_URL}|$REPO_URL|g" -e "s|\${REVISION}|$REVISION|g" -e "s|\${GAUNTLET_ENV}|$ENV_NAME|g" \
  "$ROOT/deploy/argocd/root.yaml" | kubectl apply -f -

echo "Waiting for the gauntlet application to sync and become healthy"
for _ in $(seq 1 60); do
  kubectl -n argocd get application gauntlet >/dev/null 2>&1 && break
  sleep 5
done
kubectl -n argocd wait application/gauntlet --for=jsonpath='{.status.health.status}'=Healthy --timeout=15m
kubectl -n argocd wait application/gauntlet --for=jsonpath='{.status.sync.status}'=Synced --timeout=5m

password=$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d)
echo
echo "Argo CD: kubectl -n argocd port-forward svc/argocd-server 8443:443, then https://localhost:8443"
echo "         user admin, password $password"
