"""Errors raised outside DRF views still answer with the API error format."""

from django.test import RequestFactory

from apps.core.views import not_found, server_error


def test_unknown_url_returns_json_404(client):
    response = client.get("/api/v1/does-not-exist/")

    assert response.status_code == 404
    assert response["Content-Type"] == "application/json"
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Not found.",
            "request_id": response["X-Request-ID"],
        }
    }


def test_server_error_handler_hides_details():
    response = server_error(RequestFactory().get("/api/v1/anything/"))

    assert response.status_code == 500
    assert response["Content-Type"] == "application/json"
    assert b"server_error" in response.content


def test_not_found_handler_returns_envelope():
    response = not_found(RequestFactory().get("/x/"), Exception("internal detail"))

    assert response.status_code == 404
    assert b"internal detail" not in response.content
