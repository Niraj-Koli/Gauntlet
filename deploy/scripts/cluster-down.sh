#!/usr/bin/env bash
# Delete the local k3d cluster that cluster-up.sh created (the database in Supabase stays).
set -euo pipefail
k3d cluster delete "${CLUSTER:-gauntlet}"
