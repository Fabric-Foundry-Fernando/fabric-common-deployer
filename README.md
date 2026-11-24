# fabric-common-deployer

A reusable GitHub Actions workflow that deploys Fabric artefacts to workspaces. It syncs a
Microsoft Fabric workspace to a commit in the calling repo using the Fabric Git APIs. It
authenticates to Entra ID with GitHub OIDC, so no secrets are stored.

## Usage

Each push to `dev`, `test` or `main` deploys the matching workspace (`[dev]`, `[test]`, `[prod]`).
The workspace ID comes from the `FABRIC_WORKSPACE_ID` variable on the GitHub environment.

```yaml
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

### Variables

Set these on the **caller** repo. None of them are secrets.

| Variable | Scope | Used for |
| --- | --- | --- |
| `FAB_CLIENT_ID` | Repository | Client ID of the Entra app registration the deployer signs in as. The GitHub OIDC token is exchanged for an Entra token for this app, so the app needs a federated credential for the caller repo and environment, and access to the Fabric workspaces. |
| `FAB_TENANT_ID` | Repository | Entra tenant ID that the app registration lives in. The deployer requests its token from this tenant. |
| `FABRIC_CONNECTION_ID` | Repository | ID of the Fabric GitHub connection. The deployer sets it as the workspace's Git credentials (`myGitCredentials`) so Fabric can read the caller repo before running `updateFromGit`. |
| `FABRIC_WORKSPACE_ID` | Environment (per env) | ID of the Fabric workspace to sync. Each environment (`dev-fabric`, `test-fabric`, `prod-fabric`) points at its own workspace. The deployer reads it after attaching the environment, so callers don't pass it in `with:`. |

The first three must be repository variables because the caller's `with:` block is evaluated
before the environment is attached, so it can't see environment variables.

See [docs/github-actions-setup.md](docs/github-actions-setup.md) for the one-time setup
(Actions access, environments, Entra federated credentials, the Fabric GitHub connection)
and all inputs.

## Development

```bash
python3.12 -m pip install -r fabric-cd/.deploy/requirements.txt -r fabric-cd/.deploy/requirements-test.txt
pytest fabric-cd/tests/deploy/test_deploy.py -v
```
