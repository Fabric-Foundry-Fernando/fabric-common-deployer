# Using the Fabric deployer from a GitHub repo

`fabric-common-deployer` provides a reusable workflow that syncs a Microsoft Fabric workspace to a
commit in your repo, using the Fabric Git APIs (`myGitCredentials`, `git/status`, `updateFromGit`).
It signs in to Entra ID with GitHub OIDC, so no client secrets are stored anywhere.

This page covers the one-time setup and an example caller workflow.

## 1. Allow other repos to use this one (once, by a repo admin)

`fabric-common-deployer` is private. In **Settings → Actions → General → Access**, choose
**"Accessible from repositories in the 'Fabric-Foundry-Fernando' organization"**.

Without this, calling repos fail with "workflow was not found" or "unable to resolve action".

## 2. Entra app: add a federated credential (per caller repo and environment)

In the Entra app registration used for deployments, go to
**Certificates & secrets → Federated credentials → Add credential → Other issuer**:

| Field    | Value |
|----------|-------|
| Issuer   | `https://token.actions.githubusercontent.com` |
| Subject  | `repo:Fabric-Foundry-Fernando/<caller-repo>:environment:<environment>` |
| Audience | `api://AzureADTokenExchange` |

For example, `repo:Fabric-Foundry-Fernando/sales-analytics:environment:dev-fabric`.

The subject names the **caller** repo, not `fabric-common-deployer`, so each caller repo and
environment needs its own credential.

An Entra app registration allows at most **20** federated credentials. Past that, use separate
deployment apps (for example one per team), Entra flexible federated credentials, or the
alternative below.

**Alternative:** an org admin can customise the org's OIDC subject claim to include
`job_workflow_ref`. A credential can then trust "any repo that calls this deployer workflow". This
means fewer credentials, but it's an org-wide change, so agree it with your admins first.

The app also needs access to the target workspace in Fabric (for example as Contributor or Admin).

## 3. Fabric: connect the workspace to GitHub and get a connection ID

1. Connect the Fabric workspace to the caller repo/branch (**Workspace settings → Git integration
   → GitHub**).
2. Create a Fabric connection of type **GitHub** (Source control) with a token that can read the
   repo, and share it with the deployment app.
3. Copy the connection's ID. This is the `connection_id` input.

## 4. Caller repo: environment and variables

- Create a GitHub **environment** (for example `dev-fabric`) in the caller repo. The environment
  name is part of the OIDC subject in step 2. Add protection rules here. On private repos,
  **required reviewers and wait timers need GitHub Enterprise Cloud**. On Free, Pro or Team plans
  only deployment-branch restrictions apply, so there is no approval gate. Check the org's plan
  before relying on approvals.
- Add these as **repository variables** (Settings → Secrets and variables → Actions → Variables):

  | Variable               | Value |
  |------------------------|-------|
  | `FAB_CLIENT_ID`        | Entra app (client) ID |
  | `FAB_TENANT_ID`        | Entra tenant ID |
  | `DEV_WORKSPACE_ID`     | Fabric workspace ID |
  | `FABRIC_CONNECTION_ID` | Fabric GitHub connection ID from step 3 |

  They must be **repository** variables, not environment variables. The caller job's `with:`
  block is evaluated before the reusable workflow attaches the environment, so environment-scoped
  variables are not visible there. For several environments, use distinct names (for example
  `TEST_WORKSPACE_ID`).

## 5. Example caller workflow

`.github/workflows/deploy-fabric.yml` in the caller repo:

```yaml
name: Deploy to Fabric

on:
  push:
    branches: [main]

jobs:
  deploy:
    uses: Fabric-Foundry-Fernando/fabric-common-deployer/.github/workflows/deploy-fabric-workspace.yml@main
    permissions:
      id-token: write
      contents: read
    with:
      environment: dev-fabric
      client_id: ${{ vars.FAB_CLIENT_ID }}
      tenant_id: ${{ vars.FAB_TENANT_ID }}
      workspace_id: ${{ vars.DEV_WORKSPACE_ID }}
      connection_id: ${{ vars.FABRIC_CONNECTION_ID }}
```

### Inputs

| Input           | Required | Default                    | Notes |
|-----------------|----------|----------------------------|-------|
| `environment`   | no       | `dev-fabric`               | GitHub environment in the caller repo |
| `client_id`     | yes      |                            | Entra app (client) ID |
| `tenant_id`     | yes      |                            | Entra tenant ID |
| `workspace_id`  | yes      |                            | Fabric workspace ID |
| `connection_id` | yes      |                            | Fabric GitHub connection ID |
| `commit_hash`   | no       | the caller's `github.sha`  | Commit the workspace is synced to |

**Which commit is deployed:** by default, `github.sha` of the caller run. Trigger the workflow from
the branch the Fabric workspace is connected to (`push` to that branch, or `workflow_dispatch` on
it). Don't trigger it from `pull_request`: there `github.sha` is a temporary merge commit that
isn't on the connected branch, so `updateFromGit` fails.

Deploys to the same workspace are queued, not run in parallel.

**Testing a branch of the deployer:** the reusable workflow calls the action at `@main` whatever
ref you call the workflow with. To test action changes on a branch, temporarily change that `uses:`
ref on the branch.

The caller job must grant `id-token: write`. Without it, the run fails with a message saying so.

## Troubleshooting

- **`AADSTS700213` / "No matching federated identity record found":** the subject in step 2
  doesn't match the caller repo or environment exactly. It is case-sensitive.
- **`myGitCredentials failed: 4xx`:** the connection ID is wrong, or the connection isn't shared
  with the deployment app.
- **`updateFromGit failed` / conflicts:** the deployer resolves conflicts with `PreferRemote`
  (Git wins) and allows overriding items.
