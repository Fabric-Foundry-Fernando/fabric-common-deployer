# Multi-environment deploys (dev / test / prod) — design

## Intent

Each Fabric project has three workspaces, one per environment: `<name> [dev]`, `<name> [test]`,
`<name> [prod]`. Each is connected in Fabric to one branch of the caller repo:

| Branch | Workspace          | GitHub environment |
|--------|--------------------|--------------------|
| `dev`  | `<name> [dev]`     | `dev-fabric`       |
| `test` | `<name> [test]`    | `test-fabric`      |
| `main` | `<name> [prod]`    | `prod-fabric`      |

Promotion is by pull request (dev → test → main). Merging pushes to the target branch, and that push
deploys that branch's workspace. Exactly one workspace is deployed per run.

## Goals / non-goals / anti-goals

- **Goal:** one caller workflow per repo that deploys to the right workspace on merge.
- **Goal:** the workspace ID lives with its GitHub environment, so the environment name is the
  only thing a caller chooses.
- **Goal:** a missing or wrong workspace ID fails loudly, before any sync.
- **Non-goal:** looking up workspaces by name, or deploying several environments in one run.
- **Anti-goal:** syncing the wrong workspace because of a silent fallback.

## Approaches considered

- **A1. Workspace ID as an environment variable, read inside the deployer (chosen).** Each GitHub
  environment holds `FABRIC_WORKSPACE_ID`. The caller only maps branch → environment.
- **A2. Three repo variables, mapped in the caller's `with:`.** This works, but every caller repeats
  the ID mapping, and a broken expression can fall through to the wrong ID.
- **B. Mapping in the deployer, by workspace name.** It breaks if a workspace is renamed and fixes
  the branch convention inside the deployer.
- **C. Three caller workflows, one per branch.** The same file is duplicated in every repo.

A1 relies on GitHub resolving `vars` inside a reusable workflow's job from the **caller** repo,
including the variables of the environment that job is bound to. GitHub documents this for repo
variables in reusable workflows; it is not documented as explicitly for environment variables. The
first implementation step verifies it with a real run.

## Design

### Reusable workflow and action

- `workspace_id` becomes **optional** (default `''`) in both the workflow and the action. This is
  not a breaking change.
- The deploy step passes `workspace_id: ${{ inputs.workspace_id || vars.FABRIC_WORKSPACE_ID }}`. It
  is read at step level, where the environment is bound. An explicit input still wins, so existing
  callers are unaffected.
- The `concurrency` group changes from `fabric-workspace-${{ inputs.workspace_id }}` to
  `fabric-${{ github.repository }}-${{ inputs.environment }}`. The workspace ID may not be known at
  job level any more.

### Caller (docs and example)

```yaml
on:
  push:
    branches: [dev, test, main]
jobs:
  deploy:
    uses: Fabric-Foundry-Fernando/fabric-common-deployer/.github/workflows/deploy-fabric-workspace.yml@main
    permissions: { id-token: write, contents: read }
    with:
      environment: ${{ github.ref_name == 'main' && 'prod-fabric' || format('{0}-fabric', github.ref_name) }}
      client_id: ${{ vars.FAB_CLIENT_ID }}
      tenant_id: ${{ vars.FAB_TENANT_ID }}
      connection_id: ${{ vars.FABRIC_CONNECTION_ID }}
```

Setup docs (`docs/github-actions-setup.md`):

- Three GitHub environments. Each has a `FABRIC_WORKSPACE_ID` **environment** variable and a
  deployment-branch restriction to its own branch (`prod-fabric` → `main` only).
- Three Entra federated credentials, one per environment.
- `FAB_CLIENT_ID`, `FAB_TENANT_ID` and `FABRIC_CONNECTION_ID` stay **repository** variables,
  because they are read in the caller's `with:`.
- Rewrite the note that says "environment variables are not visible" to explain where they are and
  aren't visible.
- Update the inputs table.

### Deployer guards

1. **Empty workspace ID:** the action fails with a clear `::error::` naming both sources ("pass
   `workspace_id` or set `FABRIC_WORKSPACE_ID` on environment `<env>`"), before it requests an OIDC
   token.
2. **Branch check:** a new optional script arg `--expected_branch`. When set, the script calls
   `GET /workspaces/{id}/git/connection` (after `myGitCredentials`, before `git/status`) and raises
   `RuntimeError` if `gitProviderDetails.branchName` differs from it. The action passes
   `github.ref_name` when `github.ref_type == 'branch'`, and an empty value otherwise, which skips
   the check. No workflow input is added. Confirm the response field name against the Fabric REST
   docs.

### Tests

New tests in `test_deploy_to_dev.py`:

- The branch check passes when the branches match and raises when they differ.
- The check is skipped when `--expected_branch` is not given.
- The request order is `myGitCredentials` → `git/connection` → `git/status` → `updateFromGit`.

Then run `actionlint` on the changed workflows.

## Left to the builder

- Exact error wording.
- Whether to rename `deploy_to_dev.py`. Default: don't rename it in this change.
