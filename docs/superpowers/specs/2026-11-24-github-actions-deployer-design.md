# GitHub Actions Fabric deployer — design

Date: 2026-11-24
Status: awaiting approval

## Intent

The team is moving from Azure DevOps to GitHub; only GitHub will be used going forward.
`fabric-common-deployer` (private, `Fabric-Foundry-Fernando/fabric-common-deployer`) replaces
the Azure DevOps repo `common-deployer` and its template `templates/deploy-fabric-workspace.yml`.
Fabric project repos call it to sync a Fabric workspace to a given commit via the Fabric Git APIs.

## Goals

- A reusable workflow that other repos in the org call to deploy, equivalent to the ADO template.
- Authenticate to Entra with GitHub OIDC (no client secrets, no stored tokens).
- Run the existing pytest suite in CI (the ADO pipeline never did).

## Non-goals

- Changing deploy behaviour: API calls, payloads, conflict resolution, polling stay as they are.
- Automating Entra / Fabric setup (documented, not scripted).
- Deleting the ADO repo/template — that happens separately once callers have cut over.
- Release tagging (`@v1`) — later.

## Anti-goals

- Tokens or credentials visible in logs.
- Requiring a PAT or GitHub App secret in every caller repo.

## Approaches considered

- **A. Reusable workflow checks out this repo and runs the script.** Direct port of
  `checkout: common-deployer`. Rejected: the repo is private, so the caller's `GITHUB_TOKEN`
  cannot check it out; every caller would need a PAT/App token.
- **B. Reusable workflow calls a composite action in this repo. (Chosen)** GitHub fetches the
  action using the repo's Actions access setting, the same setting needed for the reusable
  workflow itself, so no extra secret is needed.
- **C. Composite action only.** Rejected: every caller re-declares environment, permissions
  and runner, defeating a shared deployer.

## Design

### Repository layout

```
.github/
  actions/deploy-fabric-workspace/action.yml   # composite action
  workflows/deploy-fabric-workspace.yml        # reusable workflow (workflow_call)
  workflows/test.yml                           # pytest on PR + push to main
fabric-cd/.deploy/deploy_to_dev.py             # ported unchanged from common-deployer
fabric-cd/.deploy/requirements.txt
fabric-cd/.deploy/requirements-test.txt
fabric-cd/tests/__init__.py
fabric-cd/tests/deploy/__init__.py
fabric-cd/tests/deploy/test_deploy_to_dev.py   # ported unchanged
docs/github-actions-setup.md                   # one-time setup + example caller
AGENTS.md, CLAUDE.md                           # ported, updated for GitHub Actions
```

Paths under `fabric-cd/` are kept identical so the tests' `sys.path` insertion still works.

### Reusable workflow — `deploy-fabric-workspace.yml`

- `on: workflow_call` with inputs (all `string`):
  | input | required | default |
  |---|---|---|
  | `environment` | no | `dev-fabric` |
  | `client_id` | yes | |
  | `tenant_id` | yes | |
  | `workspace_id` | yes | |
  | `connection_id` | yes | |
  | `commit_hash` | no | `''` → falls back to `github.sha` |
- One job, `runs-on: ubuntu-latest`, `environment: ${{ inputs.environment }}`,
  `permissions: { id-token: write, contents: read }`.
- Single step: `uses: Fabric-Foundry-Fernando/fabric-common-deployer/.github/actions/deploy-fabric-workspace@main`
  with the inputs passed through. (A `./` path would resolve against the caller's repo.)
- Callers pass values from `vars.*`; none of the inputs are secrets.

### Composite action — `action.yml`

Same inputs (minus `environment`). Steps:

1. `actions/setup-python` with Python 3.12.
2. `pip install -r ${{ github.action_path }}/../../../fabric-cd/.deploy/requirements.txt`.
3. Request the OIDC token from `$ACTIONS_ID_TOKEN_REQUEST_URL&audience=api://AzureADTokenExchange`
   using `$ACTIONS_ID_TOKEN_REQUEST_TOKEN`; `::add-mask::` the token; expose it to the next step
   only via an env var (not a step output written to logs).
4. Run `deploy_to_dev.py` with `FEDERATED_TOKEN` set and args
   `--client_id --tenant_id --workspace_id --commit_hash --connection_id`.

Inputs are passed to shell via `env:` rather than inline `${{ }}` interpolation to avoid script
injection.

### Test workflow — `test.yml`

On `pull_request` and `push` to `main`: Python 3.12, install both requirements files, run
`pytest fabric-cd/tests/deploy/test_deploy_to_dev.py -v`.

### Setup doc — `docs/github-actions-setup.md`

- Repo Settings → Actions → General → Access: "Accessible from repositories in the
  'Fabric-Foundry-Fernando' organization".
- Entra app: add a federated credential per caller repo + environment, issuer
  `https://token.actions.githubusercontent.com`, subject
  `repo:Fabric-Foundry-Fernando/<caller>:environment:<env>`, audience `api://AzureADTokenExchange`.
  Note the alternative of customising the org OIDC subject to include `job_workflow_ref`.
- Fabric: workspace connected to the caller's GitHub repo; create a Fabric connection of type
  GitHub and use its ID as `connection_id`.
- GitHub environment (e.g. `dev-fabric`) in the caller repo, used for protection rules and the
  OIDC subject. Caller **repository** variables `FAB_CLIENT_ID`, `FAB_TENANT_ID`,
  `DEV_WORKSPACE_ID`, `FABRIC_CONNECTION_ID`. They must be repo-level because the caller job's
  `with:` is evaluated before the called job binds the environment, so environment-scoped vars
  are not visible there.
- Example caller workflow.

## Left to the builder

- Exact step names, action versions (`actions/setup-python@v5` or current major).
- Wording of the setup doc and AGENTS.md updates.
