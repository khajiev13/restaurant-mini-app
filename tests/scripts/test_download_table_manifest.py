import importlib.util
import io
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / "scripts" / "download_table_manifest.py"
SPEC = importlib.util.spec_from_file_location("download_table_manifest", SCRIPT)
assert SPEC and SPEC.loader
manifest_download = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manifest_download)


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, status: int):
        super().__init__(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()


class FakeOpener:
    def __init__(self, response: FakeResponse):
        self.response = response
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        return self.response


def test_redirect_is_rejected_without_writing_or_leaking(tmp_path, capsys):
    output = tmp_path / "manifest.json"
    opener = FakeOpener(FakeResponse(b"redirect-body-secret", status=302))

    with pytest.raises(ValueError, match="HTTP 200"):
        manifest_download.download_manifest(
            "https://restaurant.labtutor.app/api/tables/manifest",
            output,
            environ={"ADMIN_JWT": "header-secret"},
            opener=opener,
        )

    captured = capsys.readouterr()
    assert not output.exists()
    assert "header-secret" not in captured.out + captured.err
    assert "redirect-body-secret" not in captured.out + captured.err


def test_direct_200_writes_manifest_once_without_logging_secrets(tmp_path, capsys):
    output = tmp_path / "manifest.json"
    body = b'{"success":true,"data":[]}'
    opener = FakeOpener(FakeResponse(body, status=200))

    result = manifest_download.download_manifest(
        "https://restaurant.labtutor.app/api/tables/manifest",
        output,
        environ={"ADMIN_JWT": "header-secret"},
        opener=opener,
    )

    captured = capsys.readouterr()
    request, timeout = opener.requests[0]
    assert result == output
    assert output.read_bytes() == body
    assert request.get_header("Authorization") == "Bearer header-secret"
    assert request.get_header("User-agent") == "restaurant-mini-app-qr-tools/1.0"
    assert timeout == 30
    assert "header-secret" not in captured.out + captured.err
    assert body.decode() not in captured.out + captured.err


def test_existing_output_is_refused_before_network(tmp_path):
    output = tmp_path / "manifest.json"
    output.write_bytes(b"keep-existing")
    opener = FakeOpener(FakeResponse(b"replacement", status=200))

    with pytest.raises(FileExistsError):
        manifest_download.download_manifest(
            "https://restaurant.labtutor.app/api/tables/manifest",
            output,
            environ={"ADMIN_JWT": "header-secret"},
            opener=opener,
        )

    assert output.read_bytes() == b"keep-existing"
    assert opener.requests == []


def test_missing_admin_jwt_writes_nothing(tmp_path):
    output = tmp_path / "manifest.json"
    opener = FakeOpener(FakeResponse(b"unexpected", status=200))

    with pytest.raises(ValueError, match="ADMIN_JWT"):
        manifest_download.download_manifest(
            "https://restaurant.labtutor.app/api/tables/manifest",
            output,
            environ={},
            opener=opener,
        )

    assert not output.exists()
    assert opener.requests == []
