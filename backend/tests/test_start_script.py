import os
import subprocess
from pathlib import Path

START_SCRIPT = Path(__file__).resolve().parents[2] / "start.sh"


def _validate_telegram_response(tmp_path, response_body):
    env = os.environ.copy()
    env["START_SH_HELPERS_ONLY"] = "1"
    return subprocess.run(
        [
            "/bin/bash",
            "-c",
            'source "$1"; telegram_api_response_ok',
            "start-script-test",
            str(START_SCRIPT),
        ],
        cwd=tmp_path,
        env=env,
        input=response_body,
        capture_output=True,
        text=True,
        check=False,
    )


def test_telegram_api_response_rejects_ok_false_without_echoing_body(tmp_path):
    response_body = '{"ok":false,"description":"fixture-secret-response-body"}'

    result = _validate_telegram_response(tmp_path, response_body)

    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert response_body not in result.stdout + result.stderr


def test_telegram_api_response_accepts_ok_true_without_output(tmp_path):
    result = _validate_telegram_response(tmp_path, '{"ok":true}')

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
