import argparse
import os
import time

import requests
from azure.core.credentials import TokenCredential
from azure.identity import ClientAssertionCredential

FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"


def build_credential(
    tenant_id: str, client_id: str, federated_token: str
) -> ClientAssertionCredential:
    return ClientAssertionCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        func=lambda: federated_token,
    )


def update_workspace_from_git(
    workspace_id: str,
    commit_hash: str,
    connection_id: str,
    credential: TokenCredential,
    expected_branch: str | None = None,
) -> None:
    token = credential.get_token(FABRIC_SCOPE).token
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    creds_response = requests.patch(
        f"{FABRIC_API_BASE}/workspaces/{workspace_id}/git/myGitCredentials",
        headers=headers,
        json={"source": "ConfiguredConnection", "connectionId": connection_id},
        timeout=60,
    )
    if not creds_response.ok:
        raise RuntimeError(
            f"myGitCredentials failed: {creds_response.status_code} {creds_response.text}"
        )

    if expected_branch:
        _check_connected_branch(workspace_id, expected_branch, headers)

    workspace_head = _get_workspace_head(workspace_id, headers)

    response = requests.post(
        f"{FABRIC_API_BASE}/workspaces/{workspace_id}/git/updateFromGit",
        headers=headers,
        json={
            "workspaceHead": workspace_head,
            "remoteCommitHash": commit_hash,
            "conflictResolution": {
                "conflictResolutionType": "Workspace",
                "conflictResolutionPolicy": "PreferRemote",
            },
            "options": {
                "allowOverrideItems": True,
            },
        },
        timeout=60,
    )

    if response.status_code == 200:
        return

    if response.status_code == 202:
        _poll_operation(response.headers["Location"], headers)
        return

    raise RuntimeError(f"updateFromGit failed: {response.status_code} {response.text}")


def _check_connected_branch(workspace_id: str, expected_branch: str, headers: dict) -> None:
    response = requests.get(
        f"{FABRIC_API_BASE}/workspaces/{workspace_id}/git/connection",
        headers=headers,
        timeout=60,
    )
    if not response.ok:
        raise RuntimeError(
            f"GET git/connection failed: {response.status_code} {response.text}"
        )
    details = response.json().get("gitProviderDetails")
    if not details:
        raise RuntimeError(f"Workspace {workspace_id} is not connected to Git")
    branch = details.get("branchName")
    if branch != expected_branch:
        raise RuntimeError(
            f"Workspace {workspace_id} is connected to branch '{branch}' "
            f"but this run is for branch '{expected_branch}'"
        )


def _get_workspace_head(workspace_id: str, headers: dict) -> str:
    response = requests.get(
        f"{FABRIC_API_BASE}/workspaces/{workspace_id}/git/status",
        headers=headers,
        timeout=60,
    )
    if not response.ok:
        raise RuntimeError(
            f"GET git/status failed: {response.status_code} {response.text}"
        )
    head = response.json().get("workspaceHead")
    if not head:
        raise RuntimeError(
            f"workspaceHead missing in git/status response: {response.text}"
        )
    return head


def _poll_operation(location: str, headers: dict) -> None:
    retry_after = 5
    deadline = time.time() + 1800
    while time.time() < deadline:
        time.sleep(retry_after)
        status_response = requests.get(location, headers=headers, timeout=60)
        status_response.raise_for_status()
        body = status_response.json()
        status = body.get("status")
        if status == "Succeeded":
            return
        if status in ("Failed", "Cancelled"):
            raise RuntimeError(f"updateFromGit operation {status}: {body}")
        retry_after = int(status_response.headers.get("Retry-After", retry_after))
    raise RuntimeError("updateFromGit timed out after 30 minutes")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client_id", required=True)
    parser.add_argument("--tenant_id", required=True)
    parser.add_argument("--workspace_id", required=True)
    parser.add_argument("--commit_hash", required=True)
    parser.add_argument("--connection_id", required=True)
    parser.add_argument("--expected_branch", default=None)
    args = parser.parse_args()

    federated_token = os.environ["FEDERATED_TOKEN"]
    credential = build_credential(args.tenant_id, args.client_id, federated_token)
    update_workspace_from_git(
        args.workspace_id,
        args.commit_hash,
        args.connection_id,
        credential,
        expected_branch=args.expected_branch or None,
    )


if __name__ == "__main__":
    main()
