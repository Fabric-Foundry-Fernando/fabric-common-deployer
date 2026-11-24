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

See [docs/github-actions-setup.md](docs/github-actions-setup.md) for the one-time setup
(Actions access, environments, Entra federated credentials, the Fabric GitHub connection)
and all inputs.

## Development

```bash
python3.12 -m pip install -r fabric-cd/.deploy/requirements.txt -r fabric-cd/.deploy/requirements-test.txt
pytest fabric-cd/tests/deploy/test_deploy_to_dev.py -v
```
