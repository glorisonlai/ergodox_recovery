from __future__ import annotations

import http.client
import json
import threading
from collections.abc import Iterator
from importlib.resources import files
from pathlib import Path

import pytest

from ergodox_recovery.server import RecoveryHTTPServer, create_server
from ergodox_recovery.session import RecoverySession


@pytest.fixture
def running_server(tmp_path: Path) -> Iterator[tuple[RecoveryHTTPServer, int]]:
    session_path = tmp_path / "recovery.json"
    RecoverySession.new().save(session_path)
    server = create_server(session_path, port=0, token="test-token")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _request(
    port: int,
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def test_create_server_refuses_non_loopback_binding(tmp_path: Path) -> None:
    session_path = tmp_path / "recovery.json"
    RecoverySession.new().save(session_path)

    with pytest.raises(ValueError, match="only bind to 127.0.0.1"):
        create_server(session_path, host="0.0.0.0", port=0)


def test_api_requires_unpredictable_session_token(
    running_server: tuple[RecoveryHTTPServer, int],
) -> None:
    _, port = running_server

    status, _, _ = _request(port, "GET", "/api/session")
    assert status == 403
    status, headers, body = _request(
        port,
        "GET",
        "/api/session",
        headers={"X-Recovery-Token": "test-token"},
    )
    assert status == 200
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Frame-Options"] == "DENY"
    assert json.loads(body)["schema_version"] == 1


def test_non_loopback_host_is_rejected(
    running_server: tuple[RecoveryHTTPServer, int],
) -> None:
    _, port = running_server

    status, _, _ = _request(
        port,
        "GET",
        "/api/session",
        headers={"Host": "attacker.example", "X-Recovery-Token": "test-token"},
    )

    assert status == 403


def test_non_loopback_origin_is_rejected_on_mutation(
    running_server: tuple[RecoveryHTTPServer, int],
) -> None:
    server, port = running_server
    body = json.dumps(server.session.to_dict()).encode()

    status, _, _ = _request(
        port,
        "PUT",
        "/api/session",
        body=body,
        headers={
            "Content-Type": "application/json",
            "Origin": "https://attacker.example",
            "X-Recovery-Token": "test-token",
        },
    )

    assert status == 403


def test_valid_put_replaces_and_persists_validated_session(
    running_server: tuple[RecoveryHTTPServer, int],
) -> None:
    server, port = running_server
    updated = RecoverySession.from_dict(server.session.to_dict())
    updated.name = "Recovered locally"
    body = json.dumps(updated.to_dict()).encode()

    status, _, response_body = _request(
        port,
        "PUT",
        "/api/session",
        body=body,
        headers={
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{port}",
            "X-Recovery-Token": "test-token",
        },
    )

    assert status == 200
    assert json.loads(response_body)["ok"] is True
    assert RecoverySession.load(server.session_path).name == "Recovered locally"


def test_requests_do_not_emit_access_logs(
    running_server: tuple[RecoveryHTTPServer, int], capsys: pytest.CaptureFixture[str]
) -> None:
    _, port = running_server

    assert _request(port, "GET", "/")[0] == 200

    assert capsys.readouterr().err == ""


def test_capture_asset_uses_canonical_zmk_codes_and_bounded_capture() -> None:
    script = files("ergodox_recovery.web").joinpath("app.js").read_text("utf-8")
    stylesheet = files("ergodox_recovery.web").joinpath("style.css").read_text("utf-8")

    assert "KP_NUMBER_" in script
    assert "KP_N${" not in script
    assert 'Digit1: "EXCLAMATION"' in script
    assert 'BracketLeft: "LEFT_BRACE"' in script
    assert "setTimeout" in script
    assert "10000" in script
    assert 'addEventListener("dblclick"' in script
    assert 'classList.add("armed")' in script
    assert ".key.armed" in stylesheet
    assert ".key-row:nth-child(-n+5) .half.left" in stylesheet
    assert ".key-row:nth-child(-n+5) .half.right" in stylesheet
