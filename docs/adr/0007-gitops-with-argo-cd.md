# 0007: GitOps with Argo CD, an image-tag commit per release, and Sealed Secrets

**Status:** accepted

## Context

Deployments should be reproducible and reviewable, and easy to roll back. What's running should be readable from one place. And no plain-text secret should ever be committed.

## Decision

- **Packaging:** a Helm chart (`deploy/helm/gauntlet`), with one values file per environment.
- **Argo CD app-of-apps:** a root Application syncs `deploy/argocd/apps`, a small chart that renders three things: the project, the Sealed Secrets controller and the Gauntlet app. Sync is automated, with pruning and self-healing.
- **Releases:** CI builds both images on every push to `main`, tags them with the commit SHA and pushes them to GHCR. It then commits the new tags to `values-prod.yaml`. Argo CD Image Updater was the alternative; a commit keeps the record in git and needs no extra controller.
- **Ordering:** migrations run as an Argo CD Sync hook. The config and secret are in wave -2, the migration in wave -1 and the workloads in wave 0. A PreSync hook would run before the config and secret exist on a first install.
- **Secrets:** they're committed as SealedSecrets, encrypted for the cluster's controller. Locally, the bootstrap script creates a plain Secret instead.

## Consequences

- **Git is the record:** every production change is a commit, and rolling back is a revert. Drift is corrected automatically, which was tested by deleting a deployment.
- **Two commits per release:** each release adds a bot commit, and protected branches have to allow it.
- **Per-cluster keys:** sealed values are encrypted for one cluster. A new cluster means sealing again, and backing up the controller's key.
- **Argo CD needs a git server:** the local demo needs the repository pushed somewhere Argo CD can read it.
