# GitHub Actions Fabric Deployer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the Fabric deployer from the Azure DevOps repo `common-deployer` into `Fabric-Foundry-Fernando/fabric-common-deployer` as a reusable GitHub Actions workflow backed by a composite action, using GitHub OIDC.

**Architecture:** Callers `uses:` a `workflow_call` workflow that binds the GitHub environment and `id-token: write`, then calls a composite action (referenced by full repo path) which installs deps, fetches an OIDC token for audience `api://AzureADTokenExchange`, and runs the unchanged `deploy_to_dev.py`. A separate workflow runs pytest.

**Tech Stack:** GitHub Actions (reusable workflow + composite action), Python 3.12, `requests`, `azure-identity`, pytest.

**Spec:** `docs/superpowers/specs/2026-11-24-github-actions-deployer-design.md`

Source repo (read-only): `/Users/antonfernando/Dev/common-deployer`
Target repo (all edits): `/Users/antonfernando/Dev/fabric-common-deployer`

## Global Constraints

- **No `git add` / `git commit` in either repo** — a human reviews, commits and pushes. Every task ends with "leave changes uncommitted".
- Python 3.12 in all workflows.
- Python sources and tests ported **byte-for-byte**; paths under `fabric-cd/` identical to the source repo.
- Action reference in the reusable workflow: `Fabric-Foundry-Fernando/fabric-common-deployer/.github/actions/deploy-fabric-workspace@main`.
- OIDC audience: `api://AzureADTokenExchange`. Token env var name: `FEDERATED_TOKEN`.
- Reusable workflow permissions exactly `id-token: write`, `contents: read`.
- `environment` input default `dev-fabric`; `commit_hash` empty → `github.sha`.
- Never interpolate `${{ inputs.* }}` directly inside a `run:` script; pass via `env:`.
- Never echo the token; `::add-mask::` it before it is written anywhere.
- Ensure `fabric-cd/.deploy/` is not ignored by `.gitignore` (dot-directory).

## Review Focus

1. **Token leaking into logs** — the token must be masked before being written to `$GITHUB_ENV`, and `set -x` must not be used in that step. Task 3 Step 4 greps for this.
2. **`commit_hash` omitted by caller** — must deploy `github.sha` of the caller run, not pass an empty `--commit_hash`. Task 3 Step 4 checks the fallback expression.
3. **Caller forgot `id-token: write` / OIDC env vars absent** — the token step must fail with a clear message rather than calling curl with an empty URL. Task 3 Step 4 checks the guard.
4. **Action path resolution** — `github.action_path/../../../fabric-cd/.deploy` must point at the repo root's `fabric-cd`, since `action.yml` is three levels deep. Task 3 Step 4 verifies with `realpath`.
5. **Input injection** — workspace/connection IDs containing shell metacharacters must not execute. Task 3 Step 4 greps that no `${{ inputs.` appears inside a `run:` block.

---

### Task 1: Port Python deployer, tests and requirements

**Files:**
- Create (copy): `fabric-cd/.deploy/deploy_to_dev.py`, `fabric-cd/.deploy/requirements.txt`, `fabric-cd/.deploy/requirements-test.txt`, `fabric-cd/tests/__init__.py`, `fabric-cd/tests/deploy/__init__.py`, `fabric-cd/tests/deploy/test_deploy_to_dev.py`

**Interfaces:**
- Produces: `fabric-cd/.deploy/deploy_to_dev.py` CLI with args `--client_id --tenant_id --workspace_id --commit_hash --connection_id` and env `FEDERATED_TOKEN`; `requirements.txt` at that path.

- [ ] **Step 1:** Copy the six files from the source repo with `cp`, preserving paths.
- [ ] **Step 2: Verify identical** — `diff -r /Users/antonfernando/Dev/common-deployer/fabric-cd /Users/antonfernando/Dev/fabric-common-deployer/fabric-cd -x __pycache__ -x .pytest_cache` → no output.
- [ ] **Step 3: Verify not ignored** — `git -C /Users/antonfernando/Dev/fabric-common-deployer check-ignore -v fabric-cd/.deploy/deploy_to_dev.py` → no output (exit 1). If ignored, add a negation to `.gitignore`.
- [ ] **Step 4: Run tests** — in a scratchpad venv (`python3 -m venv`, any Python ≥3.10 available locally; CI pins 3.12): install both requirements files, then `pytest fabric-cd/tests/deploy/test_deploy_to_dev.py -v` from the target repo root → all pass.
- [ ] **Step 5:** Leave changes uncommitted.

### Task 2: Test workflow

**Files:**
- Create: `.github/workflows/test.yml`

**Interfaces:**
- Consumes: Task 1 requirements files and test path.

- [ ] **Step 1: Write `test.yml`** — name `Test`; triggers `pull_request` and `push` on branch `main`; `permissions: contents: read`; one job `pytest` on `ubuntu-latest`: `actions/checkout@v4`, `actions/setup-python@v5` with `python-version: '3.12'` and `cache: pip`, install both requirements files, run `pytest fabric-cd/tests/deploy/test_deploy_to_dev.py -v`.
- [ ] **Step 2: Lint** — `actionlint .github/workflows/test.yml` (run via `docker run --rm -v "$PWD":/repo -w /repo rhysd/actionlint:1.7.7` if not installed; if neither is available, `python3 -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))" <file>` and report that actionlint was skipped) → no errors.
- [ ] **Step 3:** Leave changes uncommitted.

### Task 3: Composite action and reusable deploy workflow

**Files:**
- Create: `.github/actions/deploy-fabric-workspace/action.yml`
- Create: `.github/workflows/deploy-fabric-workspace.yml`

**Interfaces:**
- Consumes: Task 1 script CLI and `requirements.txt`.
- Produces (caller contract): `uses: Fabric-Foundry-Fernando/fabric-common-deployer/.github/workflows/deploy-fabric-workspace.yml@main` with inputs `environment` (opt, `dev-fabric`), `client_id`, `tenant_id`, `workspace_id`, `connection_id` (required), `commit_hash` (opt, `''`). Composite action inputs: the same minus `environment`.

- [ ] **Step 1: Write `action.yml`** — `name: Deploy Fabric workspace`, `runs.using: composite`, inputs as above (`commit_hash` default `''`). Steps, each `shell: bash`:
  1. `actions/setup-python@v5`, `python-version: '3.12'`.
  2. Install deps: `pip install -r "$ACTION_PATH/../../../fabric-cd/.deploy/requirements.txt"` with `env: ACTION_PATH: ${{ github.action_path }}`.
  3. Get OIDC token: fail with `::error::` naming `permissions: id-token: write` if `ACTIONS_ID_TOKEN_REQUEST_URL` or `ACTIONS_ID_TOKEN_REQUEST_TOKEN` is empty; `curl -sSf -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=api://AzureADTokenExchange" | jq -r .value`; fail if the result is empty or `null`; `echo "::add-mask::$token"` **before** `echo "FEDERATED_TOKEN=$token" >> "$GITHUB_ENV"`.
  4. Deploy: `python "$ACTION_PATH/../../../fabric-cd/.deploy/deploy_to_dev.py" --client_id "$CLIENT_ID" --tenant_id "$TENANT_ID" --workspace_id "$WORKSPACE_ID" --commit_hash "$COMMIT_HASH" --connection_id "$CONNECTION_ID"`, with all values in `env:` and `COMMIT_HASH: ${{ inputs.commit_hash || github.sha }}`.
- [ ] **Step 2: Write `deploy-fabric-workspace.yml`** — `name: Deploy Fabric workspace`; `on.workflow_call.inputs` per the Produces table (all `type: string`); one job `deploy`, `name: Deploy to Fabric workspace`, `runs-on: ubuntu-latest`, `environment: ${{ inputs.environment }}`, `permissions: { id-token: write, contents: read }`; single step `uses:` the action at the Global Constraints ref, passing every input through with `with:`.
- [ ] **Step 3: Lint** — actionlint (same fallback as Task 2) on both files → no errors.
- [ ] **Step 4: Review Focus checks** (all from the target repo root):
  - `realpath .github/actions/deploy-fabric-workspace/../../../fabric-cd/.deploy/deploy_to_dev.py` → exists.
  - `grep -n '\${{ *inputs\.' .github/actions/deploy-fabric-workspace/action.yml` → every hit is under `env:` or `with:`, none inside `run:`.
  - `grep -n 'add-mask' action.yml` appears on a line before the `GITHUB_ENV` write; no `set -x`.
  - `grep -n "inputs.commit_hash || github.sha"` → present.
  - The OIDC guard emits an `::error::` mentioning `id-token: write`.
- [ ] **Step 5:** Leave changes uncommitted.

### Task 4: Setup doc, README and agent instructions

**Files:**
- Create: `docs/github-actions-setup.md`, `AGENTS.md`, `CLAUDE.md`
- Modify: `README.md`

- [ ] **Step 1: Write `docs/github-actions-setup.md`** with the sections listed in the spec's "Setup doc" section: Actions access setting; Entra federated credential (issuer `https://token.actions.githubusercontent.com`, subject `repo:Fabric-Foundry-Fernando/<caller>:environment:<env>`, audience `api://AzureADTokenExchange`, plus the `job_workflow_ref` subject-customisation alternative); Fabric GitHub connection → `connection_id`; caller environment variables `FAB_CLIENT_ID`, `FAB_TENANT_ID`, `DEV_WORKSPACE_ID`, `FABRIC_CONNECTION_ID`; and an example caller:

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

  Note in the doc: environment-scoped `vars` are not visible in the caller job's `with:` (the environment is bound inside the called workflow), so these variables must be **repository** variables, or the caller must otherwise supply them. Lint the example with actionlint as in Task 2.
- [ ] **Step 2: Port `AGENTS.md`** from the source repo, replacing ADO references: Project Map lists the two workflows, the action and the setup doc instead of `templates/deploy-fabric-workspace.yml`; adds "workflow changes: keep inputs in sync between the reusable workflow and the action; keep the full-path action ref"; drops "README is template content only".
- [ ] **Step 3: Port `CLAUDE.md`** unchanged from the source repo (`@AGENTS.md` + no-commit rule).
- [ ] **Step 4: Update `README.md`** — one paragraph on what the repo does, the caller snippet (or a link to the setup doc), and how to run tests.
- [ ] **Step 5: Final check** — re-run the Task 1 pytest command → pass; `git -C /Users/antonfernando/Dev/fabric-common-deployer status` lists only the files in this plan plus the spec/plan docs.
- [ ] **Step 6:** Leave changes uncommitted.
