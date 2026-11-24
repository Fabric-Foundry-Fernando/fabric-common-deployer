# fabric-common-deployer

A reusable GitHub Actions workflow that deploys Fabric artefacts to workspaces. It syncs a
Microsoft Fabric workspace to a commit in the calling repo using the Fabric Git APIs. It
authenticates to Entra ID with GitHub OIDC, so no secrets are stored.

## Usage

```yaml
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

See [docs/github-actions-setup.md](docs/github-actions-setup.md) for the one-time setup
(Actions access, Entra federated credentials, the Fabric GitHub connection) and all inputs.

## Development

```bash
python3.12 -m pip install -r fabric-cd/.deploy/requirements.txt -r fabric-cd/.deploy/requirements-test.txt
pytest fabric-cd/tests/deploy/test_deploy_to_dev.py -v
```
