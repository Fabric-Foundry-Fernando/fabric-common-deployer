import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.deploy"))
import deploy_to_dev


def test_build_credential_passes_correct_arguments():
    with patch("deploy_to_dev.ClientAssertionCredential") as MockCred:
        deploy_to_dev.build_credential("my-tenant", "my-client", "my-token")
        call_kwargs = MockCred.call_args[1]
        assert call_kwargs["tenant_id"] == "my-tenant"
        assert call_kwargs["client_id"] == "my-client"
        assert call_kwargs["func"]() == "my-token"


def test_update_workspace_sets_credentials_then_passes_workspace_head():
    mock_credential = MagicMock()
    mock_credential.get_token.return_value.token = "test-token"

    mock_creds_resp = MagicMock()
    mock_creds_resp.ok = True

    mock_status_resp = MagicMock()
    mock_status_resp.ok = True
    mock_status_resp.json.return_value = {"workspaceHead": "head-abc"}

    mock_update_resp = MagicMock()
    mock_update_resp.status_code = 200

    with patch("deploy_to_dev.requests.patch", return_value=mock_creds_resp) as mock_patch, \
         patch("deploy_to_dev.requests.get", return_value=mock_status_resp), \
         patch("deploy_to_dev.requests.post", return_value=mock_update_resp) as mock_post:
        deploy_to_dev.update_workspace_from_git("ws-id", "commit-abc", "conn-id", mock_credential)

        patch_body = mock_patch.call_args[1]["json"]
        assert patch_body["source"] == "ConfiguredConnection"
        assert patch_body["connectionId"] == "conn-id"

        update_body = mock_post.call_args[1]["json"]
        assert update_body["remoteCommitHash"] == "commit-abc"
        assert update_body["workspaceHead"] == "head-abc"


def test_update_workspace_polls_on_202():
    mock_credential = MagicMock()
    mock_credential.get_token.return_value.token = "test-token"

    mock_creds_resp = MagicMock()
    mock_creds_resp.ok = True

    mock_status_resp = MagicMock()
    mock_status_resp.ok = True
    mock_status_resp.json.return_value = {"workspaceHead": "head-abc"}

    mock_update_resp = MagicMock()
    mock_update_resp.status_code = 202
    mock_update_resp.headers = {"Location": "https://api.fabric.microsoft.com/v1/operations/123"}

    mock_poll_resp = MagicMock()
    mock_poll_resp.json.return_value = {"status": "Succeeded"}
    mock_poll_resp.headers = {"Retry-After": "1"}

    with patch("deploy_to_dev.requests.patch", return_value=mock_creds_resp), \
         patch("deploy_to_dev.requests.get", side_effect=[mock_status_resp, mock_poll_resp]), \
         patch("deploy_to_dev.requests.post", return_value=mock_update_resp), \
         patch("deploy_to_dev.time.sleep"):
        deploy_to_dev.update_workspace_from_git("ws-id", "commit-abc", "conn-id", mock_credential)


def test_update_workspace_raises_on_failed_operation():
    mock_credential = MagicMock()
    mock_credential.get_token.return_value.token = "test-token"

    mock_creds_resp = MagicMock()
    mock_creds_resp.ok = True

    mock_status_resp = MagicMock()
    mock_status_resp.ok = True
    mock_status_resp.json.return_value = {"workspaceHead": "head-abc"}

    mock_update_resp = MagicMock()
    mock_update_resp.status_code = 202
    mock_update_resp.headers = {"Location": "https://api.fabric.microsoft.com/v1/operations/123"}

    mock_poll_resp = MagicMock()
    mock_poll_resp.json.return_value = {"status": "Failed"}
    mock_poll_resp.headers = {}

    with patch("deploy_to_dev.requests.patch", return_value=mock_creds_resp), \
         patch("deploy_to_dev.requests.get", side_effect=[mock_status_resp, mock_poll_resp]), \
         patch("deploy_to_dev.requests.post", return_value=mock_update_resp), \
         patch("deploy_to_dev.time.sleep"):
        with pytest.raises(RuntimeError, match="Failed"):
            deploy_to_dev.update_workspace_from_git("ws-id", "commit-abc", "conn-id", mock_credential)


def test_main_reads_federated_token_from_environment(monkeypatch):
    monkeypatch.setenv("FEDERATED_TOKEN", "env-token")
    with patch("deploy_to_dev.build_credential") as mock_cred, \
         patch("deploy_to_dev.update_workspace_from_git"):
        mock_cred.return_value = MagicMock()
        with patch("sys.argv", [
            "deploy_to_dev.py",
            "--client_id", "cid",
            "--tenant_id", "tid",
            "--workspace_id", "wsid",
            "--commit_hash", "abc123",
            "--connection_id", "conn-id",
        ]):
            deploy_to_dev.main()
        mock_cred.assert_called_once_with("tid", "cid", "env-token")


def test_main_raises_when_federated_token_env_missing(monkeypatch):
    monkeypatch.delenv("FEDERATED_TOKEN", raising=False)
    with patch("sys.argv", [
        "deploy_to_dev.py",
        "--client_id", "cid",
        "--tenant_id", "tid",
        "--workspace_id", "wsid",
        "--commit_hash", "abc123",
        "--connection_id", "conn-id",
    ]):
        with pytest.raises(KeyError):
            deploy_to_dev.main()


def test_main_exits_on_missing_required_arguments():
    with patch("sys.argv", ["deploy_to_dev.py", "--client_id", "cid"]):
        with pytest.raises(SystemExit):
            deploy_to_dev.main()
