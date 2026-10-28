#!/usr/bin/env bash
# Encrypt production secrets for the cluster's Sealed Secrets controller and print the
# sealedSecret block to paste into deploy/helm/gauntlet/values-prod.yaml. The output is
# safe to commit: only that cluster can decrypt it.
#
#   deploy/scripts/seal-secrets.sh .env.prod
#
# The env file holds KEY=value lines: DATABASE_URL and GAUNTLET_SECRET_KEY at least, plus
# the model, tool and admin keys you use. Needs kubectl (pointed at the cluster) and kubeseal.
set -euo pipefail

ENV_FILE=${1:?usage: seal-secrets.sh <env file>}
NAMESPACE=${NAMESPACE:-gauntlet}

for key in DATABASE_URL GAUNTLET_SECRET_KEY; do
  grep -qE "^${key}=.+" "$ENV_FILE" || { echo "$ENV_FILE has no $key" >&2; exit 1; }
done

kubectl create secret generic gauntlet --namespace "$NAMESPACE" --from-env-file="$ENV_FILE" \
  --dry-run=client -o yaml |
  kubeseal --format yaml --controller-namespace kube-system --controller-name sealed-secrets-controller |
  awk '
    /^  encryptedData:/ { print "sealedSecret:"; print "  encryptedData:"; on = 1; next }
    on && /^    / { print; next }
    on { exit }
  '
