import base64
from unittest.mock import MagicMock, patch

import pytest
import requests

import nexudus


class TestMakeAuthHeader:
    def test_basic_auth(self):
        config = {"auth_type": "basic", "email": "user@example.com", "password": "secret"}
        expected_encoded = base64.b64encode(b"user@example.com:secret").decode()
        header = nexudus.make_auth_header(config)
        assert header == {"Authorization": f"Basic {expected_encoded}"}

    def test_bearer_auth(self):
        config = {"auth_type": "bearer", "token": "mytoken123"}
        header = nexudus.make_auth_header(config)
        assert header == {"Authorization": "Bearer mytoken123"}


class TestExtractValue:
    def test_success_returns_value(self):
        response = {"WasSuccessful": True, "Value": [1, 2, 3]}
        result = nexudus.extract_value(response)
        assert result == [1, 2, 3]

    def test_failure_exits(self):
        response = {"WasSuccessful": False, "Message": "Something went wrong"}
        with pytest.raises(SystemExit):
            nexudus.extract_value(response)

    def test_real_api_format_returns_records(self):
        response = {"Records": [1, 2, 3], "HasNextPage": False, "TotalItems": 3}
        result = nexudus.extract_value(response)
        assert result == [1, 2, 3]

    def test_real_api_format_missing_records_returns_empty(self):
        response = {"HasNextPage": False, "TotalItems": 0}
        assert nexudus.extract_value(response) == []


class TestMockResponse:
    def test_coworkercontract_url(self):
        result = nexudus._mock_response("/billing/coworkercontracts")
        assert result["WasSuccessful"] is True
        assert len(result["Value"]) == 5

    def test_coworkerinvoice_url(self):
        result = nexudus._mock_response("/billing/coworkerinvoices")
        assert result["WasSuccessful"] is True
        assert len(result["Value"]) == 4

    def test_coworkers_url(self):
        result = nexudus._mock_response("/spaces/coworkers")
        assert result["WasSuccessful"] is True
        assert len(result["Value"]) == 3

    def test_unknown_url_returns_empty(self):
        result = nexudus._mock_response("/unknown/endpoint")
        assert result["WasSuccessful"] is True
        assert result["Value"] == []
        assert result["HasNextPage"] is False


class TestApiGet:
    def _make_response(self, status_code, data, ok=True, headers=None):
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.ok = ok
        mock_resp.json.return_value = data
        mock_resp.headers = headers or {}
        return mock_resp

    def test_success(self):
        mock_resp = self._make_response(200, {"result": "ok"})
        with patch("nexudus.requests.get", return_value=mock_resp):
            result = nexudus.api_get("http://example.com", {})
        assert result == {"result": "ok"}

    def test_429_then_success(self):
        mock_429 = self._make_response(429, {}, ok=False, headers={"Retry-After": "0"})
        mock_200 = self._make_response(200, {"result": "ok"})
        with patch("nexudus.requests.get", side_effect=[mock_429, mock_200]):
            with patch("nexudus.time.sleep"):
                result = nexudus.api_get("http://example.com", {})
        assert result == {"result": "ok"}

    def test_non_2xx_exits(self):
        mock_resp = self._make_response(500, {}, ok=False)
        with patch("nexudus.requests.get", return_value=mock_resp):
            with pytest.raises(SystemExit):
                nexudus.api_get("http://example.com", {})

    def test_request_exception_exits(self):
        with patch(
            "nexudus.requests.get",
            side_effect=requests.RequestException("network error"),
        ):
            with pytest.raises(SystemExit):
                nexudus.api_get("http://example.com", {})
