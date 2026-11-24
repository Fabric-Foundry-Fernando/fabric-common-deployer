import os
import sys
import pytest
from contextlib import contextmanager
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


def _ok_resp(json_body=None):
    resp = MagicMock()
    resp.ok = True
    resp.json.return_value = json_body or {}
    return resp


def _connection_resp(branch_name):
    return _ok_resp({"gitProviderDetails": {"branchName": branch_name}})


@contextmanager
def _fabric_api(get_responses):
    """Patch the Fabric HTTP calls; yields (mock_get, mock_post)."""
    mock_update_resp = MagicMock()
    mock_update_resp.status_code = 200
    with patch("deploy_to_dev.requests.patch", return_value=_ok_resp()), \
         patch("deploy_to_dev.requests.get", side_effect=get_responses) as mock_get, \
         patch("deploy_to_dev.requests.post", return_value=mock_update_resp) as mock_post:
        yield mock_get, mock_post


def _update(expected_branch):
    credential = MagicMock()
    credential.get_token.return_value.token = "test-token"
    deploy_to_dev.update_workspace_from_git(
        "ws-id", "commit-abc", "conn-id", credential, expected_branch=expected_branch
    )


_HEAD = {"workspaceHead": "head-abc"}


def test_branch_check_passes_when_branch_matches():
    with _fabric_api([_connection_resp("dev"), _ok_resp(_HEAD)]) as (mock_get, mock_post):
        _update("dev")
    get_urls = [c.args[0] for c in mock_get.call_args_list]
    assert get_urls[0].endswith("/workspaces/ws-id/git/connection")
    assert get_urls[1].endswith("/workspaces/ws-id/git/status")
    mock_post.assert_called_once()


def test_branch_check_raises_on_mismatch():
    with _fabric_api([_connection_resp("test"), _ok_resp(_HEAD)]) as (_, mock_post):
        with pytest.raises(RuntimeError, match="dev") as excinfo:
            _update("dev")
    assert "test" in str(excinfo.value)
    mock_post.assert_not_called()


def test_branch_check_raises_when_workspace_not_git_connected():
    with _fabric_api([_ok_resp({"gitProviderDetails": None}), _ok_resp(_HEAD)]) as (_, mock_post):
        with pytest.raises(RuntimeError, match="not connected"):
            _update("dev")
    mock_post.assert_not_called()


def test_branch_check_raises_on_connection_http_error():
    conn_resp = MagicMock()
    conn_resp.ok = False
    conn_resp.status_code = 403
    conn_resp.text = "forbidden"
    with _fabric_api([conn_resp, _ok_resp(_HEAD)]) as (mock_get, mock_post):
        with pytest.raises(RuntimeError, match="403"):
            _update("dev")
    assert mock_get.call_count == 1
    mock_post.assert_not_called()


@pytest.mark.parametrize("expected_branch", [None, ""])
def test_branch_check_skipped_when_expected_branch_not_given(expected_branch):
    with _fabric_api([_ok_resp(_HEAD)]) as (mock_get, mock_post):
        _update(expected_branch)
    get_urls = [c.args[0] for c in mock_get.call_args_list]
    assert not any("/git/connection" in url for url in get_urls)
    mock_post.assert_called_once()


_MAIN_ARGV = [
    "deploy_to_dev.py",
    "--client_id", "cid",
    "--tenant_id", "tid",
    "--workspace_id", "wsid",
    "--commit_hash", "abc123",
    "--connection_id", "conn-id",
]


def test_main_passes_expected_branch(monkeypatch):
    monkeypatch.setenv("FEDERATED_TOKEN", "env-token")
    with patch("deploy_to_dev.build_credential"), \
         patch("deploy_to_dev.update_workspace_from_git") as mock_update, \
         patch("sys.argv", _MAIN_ARGV + ["--expected_branch", "dev"]):
        deploy_to_dev.main()
    assert mock_update.call_args.kwargs["expected_branch"] == "dev"


def test_main_expected_branch_defaults_to_none(monkeypatch):
    monkeypatch.setenv("FEDERATED_TOKEN", "env-token")
    with patch("deploy_to_dev.build_credential"), \
         patch("deploy_to_dev.update_workspace_from_git") as mock_update, \
         patch("sys.argv", _MAIN_ARGV):
        deploy_to_dev.main()
    assert mock_update.call_args.kwargs["expected_branch"] is None
