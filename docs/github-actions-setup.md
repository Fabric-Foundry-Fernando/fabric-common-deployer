# Using the Fabric deployer from a GitHub repo

`fabric-common-deployer` provides a reusable workflow that syncs a Microsoft Fabric workspace to a
commit in your repo, using the Fabric Git APIs (`myGitCredentials`, `git/status`, `updateFromGit`).
It signs in to Entra ID with GitHub OIDC, so no client secrets are stored anywhere.

Each project has one Fabric workspace per environment, for example `Sales [dev]`, `Sales [test]` and
`Sales [prod]`. Each workspace is connected to one branch of the caller repo, and merging a pull
request into that branch deploys that workspace. Each run deploys exactly one workspace.

| Branch | Workspace       | GitHub environment |
|--------|-----------------|--------------------|
| `dev`  | `<name> [dev]`  | `dev-fabric`       |
| `test` | `<name> [test]` | `test-fabric`      |
| `main` | `<name> [prod]` | `prod-fabric`      |

To promote a change, merge a PR from `dev` into `test`, then from `test` into `main`.

This page covers the one-time setup and an example caller workflow.

## 1. Allow other repos to use this one (once, by a repo admin)

`fabric-common-deployer` is private. In **Settings → Actions → General → Access**, choose
**"Accessible from repositories in the 'Fabric-Foundry-Fernando' organization"**.

Without this, calling repos fail with "workflow was not found" or "unable to resolve action".

## 2. Entra app: add federated credentials (per caller repo and environment)

In the Entra app registration used for deployments, go to
**Certificates & secrets → Federated credentials → Add credential → Other issuer**, and add one
credential for each environment (`dev-fabric`, `test-fabric`, `prod-fabric`):

| Field    | Value |
|----------|-------|
| Issuer   | `https://token.actions.githubusercontent.com` |
| Subject  | `repo:Fabric-Foundry-Fernando/<caller-repo>:environment:<environment>` |
| Audience | `api://AzureADTokenExchange` |

For example, `repo:Fabric-Foundry-Fernando/sales-analytics:environment:prod-fabric`.

The subject names the **caller** repo, not `fabric-common-deployer`, so each caller repo and
environment needs its own credential. That's three per caller repo.

An Entra app registration allows at most **20** federated credentials (about six caller repos with
three environments each). Past that, use separate deployment apps (for example one per team),
Entra flexible federated credentials, or the alternative below.

**Alternative:** an org admin can customise the org's OIDC subject claim to include
`job_workflow_ref`. A credential can then trust "any repo that calls this deployer workflow". This
means fewer credentials, but it's an org-wide change, so agree it with your admins first.

The app also needs access to each target workspace in Fabric (for example as Contributor or Admin).

## 3. Fabric: connect each workspace to its branch and get a connection ID

1. Connect each Fabric workspace to the caller repo, on its own branch: `[dev]` to `dev`, `[test]`
   to `test`, `[prod]` to `main` (**Workspace settings → Git integration → GitHub**).
2. Create a Fabric connection of type **GitHub** (Source control) with a token that can read the
   repo, and share it with the deployment app.
3. Copy the connection's ID. This is the `connection_id` input. One connection can serve all three
   workspaces.

## 4. Caller repo: environments and variables

Create three GitHub **environments** in the caller repo: `dev-fabric`, `test-fabric` and
`prod-fabric`. The environment name is part of the OIDC subject in step 2. For each one:

- Add an **environment variable** `FABRIC_WORKSPACE_ID` set to that environment's Fabric
  workspace ID.
- Under **Deployment branches**, allow only its own branch (`dev`, `test` or `main`). Then
  `prod-fabric` can only be deployed from `main`.
- Add any other protection rules. On private repos, **required reviewers and wait timers need
  GitHub Enterprise Cloud**. On Free, Pro or Team plans only deployment-branch restrictions apply,
  so there is no approval gate. Check the org's plan before relying on approvals.

Add these as **repository variables** (Settings → Secrets and variables → Actions → Variables):

| Variable               | Value |
|------------------------|-------|
| `FAB_CLIENT_ID`        | Entra app (client) ID |
| `FAB_TENANT_ID`        | Entra tenant ID |
| `FABRIC_CONNECTION_ID` | Fabric GitHub connection ID from step 3 |

**Why some variables are repository variables and one is an environment variable:**

- The caller job's `with:` block is evaluated before the deployer attaches the environment, so it
  can only see repository variables. Anything you pass in `with:` must be a repository variable.
- The deployer reads `FABRIC_WORKSPACE_ID` inside its own job, after the environment is attached.
  That's why it lives on the environment.

## 5. Example caller workflow

`.github/workflows/deploy-fabric.yml` in the caller repo:

```yaml
name: Deploy to Fabric

on:
  push:
    branches: [dev, test, main]

jobs:
  deploy:
    uses: Fabric-Foundry-Fernando/fabric-common-deployer/.github/workflows/deploy-fabric-workspace.yml@main
    permissions:
      id-token: write
      contents: read
    with:
      environment: ${{ github.ref_name == 'main' && 'prod-fabric' || format('{0}-fabric', github.ref_name) }}
      client_id: ${{ vars.FAB_CLIENT_ID }}
      tenant_id: ${{ vars.FAB_TENANT_ID }}
      connection_id: ${{ vars.FABRIC_CONNECTION_ID }}
```

A push to `dev` deploys with `dev-fabric`, a push to `test` with `test-fabric`, and a push to
`main` with `prod-fabric`. Each environment's `FABRIC_WORKSPACE_ID` picks the workspace.

Keep `branches:` to exactly `dev`, `test` and `main`. Any other branch maps to an environment that
doesn't exist, such as `feature-x-fabric`. GitHub creates that environment automatically and empty,
and the run fails with "No workspace ID".

### Inputs

| Input           | Required | Default                                  | Notes |
|-----------------|----------|------------------------------------------|-------|
| `environment`   | no       | `dev-fabric`                             | GitHub environment in the caller repo |
| `client_id`     | yes      |                                          | Entra app (client) ID |
| `tenant_id`     | yes      |                                          | Entra tenant ID |
| `workspace_id`  | no       | the environment's `FABRIC_WORKSPACE_ID`  | Fabric workspace ID. Overrides the environment variable if passed |
| `connection_id` | yes      |                                          | Fabric GitHub connection ID |
| `commit_hash`   | no       | the caller's `github.sha`                | Commit the workspace is synced to |

**Which commit is deployed:** by default, `github.sha` of the caller run. Trigger the workflow from
the branch the Fabric workspace is connected to (`push` to that branch, or `workflow_dispatch` on
it). Don't trigger it from `pull_request`: there `github.sha` is a temporary merge commit that
isn't on the connected branch, so `updateFromGit` fails.

**Branch check:** before syncing, the deployer checks that the workspace is connected to the branch
that triggered the run, and stops if not. This catches a `FABRIC_WORKSPACE_ID` that points at
another environment's workspace. The check is skipped for non-branch triggers such as tags, and when you pass an explicit
`commit_hash`.

Deploys are queued per caller repo and environment, not run in parallel.

**Testing a branch of the deployer:** the reusable workflow calls the action at `@main` whatever
ref you call the workflow with. To test action changes on a branch, temporarily change that `uses:`
ref on the branch.

The caller job must grant `id-token: write`. Without it, the run fails with a message saying so.

## Troubleshooting

- **`AADSTS700213` / "No matching federated identity record found":** the subject in step 2
  doesn't match the caller repo or environment exactly. It is case-sensitive. Check there's a
  credential for the environment that failed.
- **`No workspace ID`:** the environment has no `FABRIC_WORKSPACE_ID` variable, or the push was to
  a branch that isn't mapped to an environment.
- **`connected to branch 'X' but this run is for branch 'Y'`:** the environment's
  `FABRIC_WORKSPACE_ID` is the ID of another environment's workspace.
- **`not connected to Git`:** the workspace isn't connected to the repo. See step 3.
- **`myGitCredentials failed: 4xx`:** the connection ID is wrong, or the connection isn't shared
  with the deployment app.
- **`updateFromGit failed` / conflicts:** the deployer resolves conflicts with `PreferRemote`
  (Git wins) and allows overriding items.
