# AGENTS.md

Agent instructions for `fabric-common-deployer`.

## Purpose

- Maintain the Fabric deployment utility in `fabric-cd/.deploy/deploy.py` and its tests in `fabric-cd/tests/deploy/`.
- Maintain the reusable GitHub Actions workflow and composite action that other repos call to deploy.
- Prioritize safe, test-backed changes to Git-to-Fabric workspace sync behavior.

## Project Map

- `fabric-cd/.deploy/deploy.py`: CLI script that authenticates with a federated token and calls Fabric Git APIs (`myGitCredentials`, `git/status`, `updateFromGit`).
- `fabric-cd/tests/deploy/test_deploy.py`: unit tests using `pytest` and `unittest.mock`.
- `.github/workflows/deploy-fabric-workspace.yml`: reusable workflow (`workflow_call`) that callers `uses:`. Binds the GitHub environment and `id-token: write`, then calls the composite action.
- `.github/actions/deploy-fabric-workspace/action.yml`: composite action. It sets up Python 3.12, installs requirements, then, in one step, gets a GitHub OIDC token (audience `api://AzureADTokenExchange`) and runs the script with it as `FEDERATED_TOKEN`.
- `.github/workflows/test.yml`: runs the pytest suite on PRs and pushes to `main`.
- `docs/github-actions-setup.md`: one-time setup (Actions access, Entra federated credentials, Fabric connection) and an example caller.

## Environment

- Use Python 3.12 to match CI.
- Install runtime deps from `fabric-cd/.deploy/requirements.txt`.
- Install test deps from `fabric-cd/.deploy/requirements-test.txt`.

## Commands

From repo root:

```bash
python3.12 -m pip install -r fabric-cd/.deploy/requirements-test.txt
python3.12 -m pip install -r fabric-cd/.deploy/requirements.txt
pytest fabric-cd/tests/deploy/test_deploy.py -v
actionlint .github/workflows/*.yml
```

## Coding Conventions

- Keep the script as a small, explicit CLI module: parse args in `main()`, keep API operations in helper functions.
- Raise `RuntimeError` with clear context on non-success API responses.
- Preserve Fabric API constants and request shapes unless requirements explicitly change.
- Keep conflict resolution semantics explicit when editing `updateFromGit` payload fields.

## Workflow Conventions

- Keep inputs in sync between the reusable workflow and the composite action (names, required flags, defaults).
- The reusable workflow must reference the action by its full path (`Fabric-Foundry-Fernando/fabric-common-deployer/.github/actions/deploy-fabric-workspace@<ref>`). A `./` path resolves against the caller's repo.
- The action ref in the reusable workflow does not follow the caller's ref. When tagging a release (`vN`), change `@main` to `@vN` in the tagged commit.
- The action locates the script via `github.action_path/../../../fabric-cd/.deploy`. If you move the action or the script, update that path.
- Pass `${{ inputs.* }}` to shell steps through `env:`, never inline inside `run:` (script injection).
- Mask the OIDC token (`::add-mask::`) immediately. Fetch it and use it in the same step, and never write it to `GITHUB_ENV`/`GITHUB_OUTPUT`. Never `set -x` in that step.
- Changing workflow inputs is a breaking change for callers: update `docs/github-actions-setup.md` in the same change.

## Testing Conventions

- Mock external calls at module import paths used by the code under test (for example `deploy.requests.post`).
- For polling behavior (`202` responses), always mock both polling responses and `time.sleep`.
- Use `monkeypatch` for environment variable tests (`FEDERATED_TOKEN`).
- If you change CLI args or API request payloads, update/add tests in `fabric-cd/tests/deploy/test_deploy.py` in the same change. Also update the composite action's arguments.

## Pitfalls

- Tests rely on `sys.path` insertion to import from `fabric-cd/.deploy`; avoid reorganizing paths without updating tests.
- `FEDERATED_TOKEN` is required at runtime; local direct script runs fail without it.
- `202 Accepted` means asynchronous operation: do not treat it as failure.
- `workspaceHead` from `git/status` is required before `updateFromGit`; preserve this flow.
- The OIDC subject is the caller repo, not this one. Entra federated credentials are configured per caller repo and environment.

## Change Checklist

- Run `pytest fabric-cd/tests/deploy/test_deploy.py -v`.
- Run `actionlint` on changed workflows.
- Confirm no credentials or tokens are logged.
- Keep changes scoped to deployment behavior, workflows and tests unless explicitly asked otherwise.
