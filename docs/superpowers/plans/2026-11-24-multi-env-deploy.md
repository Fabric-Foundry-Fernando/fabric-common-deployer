# Multi-environment deploys Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a caller deploy to its dev, test or prod Fabric workspace by choosing only a GitHub
environment, with the workspace ID stored as that environment's `FABRIC_WORKSPACE_ID` variable.

**Architecture:**
- The reusable workflow makes `workspace_id` optional and falls back to `vars.FABRIC_WORKSPACE_ID`
  at step level, where the environment is bound.
- The composite action fails early on an empty ID and passes the triggering branch to the script.
- The script checks that branch against the workspace's Git connection before syncing.

**Tech Stack:** Python 3.12, `requests`, `pytest` and `unittest.mock`, GitHub Actions (reusable
workflow and composite action), `actionlint`.

**Spec:** `docs/superpowers/specs/2026-11-24-multi-env-deploy-design.md`

## Global Constraints

- **No commits:** never `git add` or `git commit` (from `CLAUDE.md`). Each task ends by leaving its
  changes in the working tree for human review.
- **Workflow and action inputs stay in sync:** same names, required flags and defaults.
- **No inline inputs:** pass `${{ inputs.* }}` and `${{ vars.* }}` to shell steps through `env:`,
  never inline in `run:`.
- **OIDC token handling is unchanged:** mask it immediately, fetch and use it in one step, never
  `set -x`.
- **Variable name:** the environment variable is exactly `FABRIC_WORKSPACE_ID`.
- **Environment names:** `dev-fabric`, `test-fabric` and `prod-fabric`. Branches map
  `dev` → `dev-fabric`, `test` → `test-fabric`, `main` → `prod-fabric`.
- **Error style:** non-success API responses raise `RuntimeError` with clear context.
- **Script stays where it is:** do not rename `deploy_to_dev.py`.

## Review Focus

1. **Workspace not connected to Git.** `git/connection` returns `gitProviderDetails: null`. Expect a
   `RuntimeError` saying the workspace isn't connected, not a `TypeError` or `KeyError`. The test
   goes in Task 1.
2. **`git/connection` returns a non-2xx response** (403 or 404). Expect a `RuntimeError` with the
   status and body, and no `git/status` or `updateFromGit` call. The test goes in Task 1.
3. **Push to a branch outside the mapping.** GitHub auto-creates a missing environment such as
   `feature-x-fabric`, which has no `FABRIC_WORKSPACE_ID`. Expect the empty-ID guard to fail with a
   message naming the environment. The guard goes in Task 2; the warning to keep
   `branches: [dev, test, main]` goes in Task 3.
4. **Both the input and the environment variable are set.** Expect the explicit `workspace_id`
   input to win, so existing callers are unchanged. Task 2 handles this through the order of the
   `||` expression.
5. **Non-branch trigger** (for example a tag). Expect the branch check to be skipped, not to fail.
   Task 2 handles this by passing an empty `EXPECTED_BRANCH`, and a Task 1 test shows that empty
   means skip.

---

### Task 0: Verify the assumptions (manual, human-run)

The design depends on two facts that GitHub and Microsoft don't clearly document. Confirm both
before Task 2.

**Files:**
- Create, then delete, on a throwaway branch `probe/env-vars` of this repo:
  `.github/workflows/probe-env-vars.yml`

- [ ] **Step 1: Write the probe reusable workflow**

```yaml
name: Probe env vars
on:
  workflow_call:
    inputs:
      environment: { type: string, required: true }
jobs:
  probe:
    runs-on: ubuntu-latest
    environment: ${{ inputs.environment }}
    steps:
      - env:
          WS: ${{ vars.FABRIC_WORKSPACE_ID }}
        run: |
          if [ -n "$WS" ]; then echo "FABRIC_WORKSPACE_ID visible: $WS"; else echo "::error::FABRIC_WORKSPACE_ID empty"; exit 1; fi
```

- [ ] **Step 2: Run it from a caller repo**

In a caller repo, create the `dev-fabric` environment with an environment variable
`FABRIC_WORKSPACE_ID` set to the dev workspace ID. Add a `workflow_dispatch` workflow that `uses:`
`Fabric-Foundry-Fernando/fabric-common-deployer/.github/workflows/probe-env-vars.yml@probe/env-vars`
with `environment: dev-fabric`, and run it.

Expected: the log shows `FABRIC_WORKSPACE_ID visible: <dev id>`. If it fails, stop and return to
the design. A fallback is to pass the ID from the caller.

- [ ] **Step 3: Confirm the `git/connection` response shape**

Check the Fabric REST docs (Git → Get Connection), or call
`GET https://api.fabric.microsoft.com/v1/workspaces/{dev-id}/git/connection` as the deploy app.

Expected: the response includes `gitProviderDetails.branchName` with the plain branch name (`dev`,
not `refs/heads/dev`). If the field name differs, use the real one in Task 1.

- [ ] **Step 4: Clean up**

Delete the `probe/env-vars` branch and the caller's probe workflow.

---

### Task 1: Branch check in the script

**Files:**
- Modify: `fabric-cd/.deploy/deploy_to_dev.py`
- Test: `fabric-cd/tests/deploy/test_deploy_to_dev.py`

**Interfaces:**
- Produces:
  - `update_workspace_from_git(workspace_id: str, commit_hash: str, connection_id: str, credential: TokenCredential, expected_branch: str | None = None) -> None`
  - `_check_connected_branch(workspace_id: str, expected_branch: str, headers: dict) -> None`
  - CLI arg `--expected_branch`: optional, default `None`. An empty string is treated as not set.

- [ ] **Step 1: Write the failing tests**

Follow the existing mock style: `deploy_to_dev.requests.patch`, `.get` and `.post`, and a
`MagicMock` credential.

- `test_branch_check_passes_when_branch_matches`:
  - Mock `requests.get` with `side_effect=[conn_resp, status_resp]`. `conn_resp.ok = True` and
    `conn_resp.json()` returns `{"gitProviderDetails": {"branchName": "dev"}}`.
  - Call with `expected_branch="dev"`.
  - Assert `mock_post` was called once.
  - Assert the first GET URL ends with `/workspaces/ws-id/git/connection` and the second ends with
    `/git/status`.
- `test_branch_check_raises_on_mismatch`:
  - `branchName` is `"test"` and `expected_branch` is `"dev"`.
  - `pytest.raises(RuntimeError, match="dev")`, and the message also contains `"test"`.
  - Assert `mock_post.assert_not_called()`.
- `test_branch_check_raises_when_workspace_not_git_connected`:
  - The response JSON is `{"gitProviderDetails": None}`.
  - `pytest.raises(RuntimeError, match="not connected")`, and `mock_post.assert_not_called()`.
- `test_branch_check_raises_on_connection_http_error`:
  - `conn_resp.ok = False`, `status_code = 403`, `text = "forbidden"`.
  - `pytest.raises(RuntimeError, match="403")`.
  - Assert `requests.get` was called exactly once, and `mock_post.assert_not_called()`.
- `test_branch_check_skipped_when_expected_branch_not_given`:
  - Call without `expected_branch`, and again with `expected_branch=""`.
  - In both runs, assert no GET URL contains `/git/connection`.
- `test_main_passes_expected_branch`:
  - Use the `sys.argv` style of `test_main_reads_federated_token_from_environment`, plus
    `"--expected_branch", "dev"`.
  - Assert the patched `update_workspace_from_git` was called with `expected_branch="dev"`.
- `test_main_expected_branch_defaults_to_none`:
  - Run without the arg.
  - Assert `update_workspace_from_git` was called with `expected_branch=None`.

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `pytest fabric-cd/tests/deploy/test_deploy_to_dev.py -v`

Expected: the 7 new tests FAIL (unexpected keyword `expected_branch` or unrecognised argument). The
existing 7 still PASS.

- [ ] **Step 3: Implement the branch check**

- `_check_connected_branch` sends a GET to `f"{FABRIC_API_BASE}/workspaces/{workspace_id}/git/connection"`
  with `timeout=60`. It raises `RuntimeError` if:
  - the response is not OK. The message is
    `f"GET git/connection failed: {status_code} {text}"`.
  - `gitProviderDetails` is missing or null. The message contains `"not connected to Git"`.
  - `branchName != expected_branch`. The message names both branches, for example
    `"Workspace ws-id is connected to branch 'test' but this run is for branch 'dev'"`.
- `update_workspace_from_git` calls it after `myGitCredentials` and before `_get_workspace_head`,
  only when `expected_branch` is truthy.
- `main()` adds `parser.add_argument("--expected_branch", default=None)` and passes
  `expected_branch=args.expected_branch or None`.

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `pytest fabric-cd/tests/deploy/test_deploy_to_dev.py -v`

Expected: all 14 PASS.

- [ ] **Step 5: Leave for review**

Do not commit. List the changed files in the task report.

---

### Task 2: Workflow and action read the environment's workspace ID

**Files:**
- Modify: `.github/workflows/deploy-fabric-workspace.yml`
- Modify: `.github/actions/deploy-fabric-workspace/action.yml`

**Interfaces:**
- Consumes: the script arg `--expected_branch` from Task 1.
- Produces: `workspace_id` becomes optional (`required: false`, `default: ''`) in **both** files,
  and its description mentions the `FABRIC_WORKSPACE_ID` fallback.

- [ ] **Step 1: Update the reusable workflow**

- `workspace_id` input: `required: false`, `default: ''`. Description: "Fabric workspace ID to
  update. Defaults to the bound environment's `FABRIC_WORKSPACE_ID` variable."
- Change `concurrency.group` to `fabric-${{ github.repository }}-${{ inputs.environment }}`. Keep
  `cancel-in-progress: false`, and update the comment to say deploys are queued per repo and
  environment.
- In the step's `with:`, set `workspace_id: ${{ inputs.workspace_id || vars.FABRIC_WORKSPACE_ID }}`.
  Put the input first so an explicit input wins.

- [ ] **Step 2: Update the composite action**

- `workspace_id` input: `required: false`, `default: ''`, with the same description as the
  workflow.
- Deploy step `env:`: add
  `EXPECTED_BRANCH: ${{ github.ref_type == 'branch' && github.ref_name || '' }}`.
- At the very top of `run:`, before the OIDC check and the token fetch:

```bash
if [ -z "${WORKSPACE_ID:-}" ]; then
  echo "::error::No workspace ID. Pass 'workspace_id' or set the FABRIC_WORKSPACE_ID variable on the GitHub environment this job runs in."
  exit 1
fi
```

  The message doesn't name the environment. The action has no environment-name input, and the run
  UI already shows which environment is bound. Don't add an input just for this message.
- Add `--expected_branch "$EXPECTED_BRANCH"` to the script call. An empty value skips the check
  (Task 1).

- [ ] **Step 3: Lint**

Run: `actionlint .github/workflows/*.yml`

Expected: no output, exit 0. (`actionlint` doesn't lint composite actions. Re-read `action.yml`
against the Global Constraints instead.)

- [ ] **Step 4: Re-run the unit tests**

Run: `pytest fabric-cd/tests/deploy/test_deploy_to_dev.py -v`

Expected: all PASS.

- [ ] **Step 5: Leave for review**

Do not commit.

---

### Task 3: Setup docs

**Files:**
- Modify: `docs/github-actions-setup.md`
- Modify: `AGENTS.md` (only the "Workflow Conventions" bullet about inputs, if wording needs it)

- [ ] **Step 1: Rewrite section 2 (federated credentials)**

Use three credentials per caller repo, one for each of `dev-fabric`, `test-fabric` and
`prod-fabric`. Give an example subject for `prod-fabric`.

- [ ] **Step 2: Rewrite section 4 (environments and variables)**

- Three environments. Each has an **environment variable** `FABRIC_WORKSPACE_ID`, and its
  deployment branches are limited to its own branch (`dev`, `test`, `main`).
- `FAB_CLIENT_ID`, `FAB_TENANT_ID` and `FABRIC_CONNECTION_ID` stay **repository** variables.
  Remove `DEV_WORKSPACE_ID`.
- Replace the "must be repository variables" paragraph. The caller's `with:` can't see
  environment variables, but the deployer reads `FABRIC_WORKSPACE_ID` inside its own job, where
  the environment is attached.

- [ ] **Step 3: Replace the example caller in section 5**

Use the caller YAML from the spec's "Caller" section verbatim: push to `[dev, test, main]`, the
environment expression, and no `workspace_id`.

Add a note: keep the `branches:` list to exactly the mapped branches. Any other branch maps to a
non-existent environment, which GitHub creates automatically and empty, and the run then fails
with "No workspace ID".

Add the promotion flow in one line: merge a PR dev → test, then test → main.

- [ ] **Step 4: Update the inputs table**

`workspace_id`: required "no", default "environment's `FABRIC_WORKSPACE_ID`".

Add a sentence: deploys are queued per repo and environment.

- [ ] **Step 5: Add troubleshooting entries**

- `No workspace ID`: the environment is missing `FABRIC_WORKSPACE_ID`, or the push was to an
  unmapped branch.
- `connected to branch 'X' but this run is for branch 'Y'`: the environment's
  `FABRIC_WORKSPACE_ID` points at another environment's workspace.
- `not connected to Git`: connect the workspace (section 3).

- [ ] **Step 6: Leave for review**

Do not commit.

---

### Task 4: End-to-end check on dev (manual, human-run)

- [ ] **Step 1:** On a deployer branch, temporarily change the action `uses:` ref in
  `deploy-fabric-workspace.yml` from `@main` to `@<branch>`. The setup docs describe this.
- [ ] **Step 2:** Point the caller's workflow at `deploy-fabric-workspace.yml@<branch>` and push a
  change to `dev`.

  Expected: the run binds `dev-fabric`, syncs `<name> [dev]` and succeeds.
- [ ] **Step 3:** Temporarily set `dev-fabric`'s `FABRIC_WORKSPACE_ID` to the test workspace ID and
  re-run.

  Expected: it fails with the branch-mismatch error, and the test workspace is unchanged. Restore
  the variable afterwards.
- [ ] **Step 4:** Revert the temporary `@<branch>` ref before merging.
