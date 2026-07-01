from types import SimpleNamespace

from app.services import visitors


def _request(headers: dict[str, str], host: str = "127.0.0.1") -> SimpleNamespace:
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))


def test_client_ip_prefers_cloudflare_public_ip() -> None:
    request = _request(
        {
            "cf-connecting-ip": "1.1.1.1",
            "x-forwarded-for": "127.0.0.1",
            "x-real-ip": "127.0.0.1",
        }
    )

    assert visitors._client_ip(request) == "1.1.1.1"


def test_client_ip_uses_first_public_forwarded_ip() -> None:
    request = _request(
        {"x-forwarded-for": "10.0.0.2, 8.8.8.8, 127.0.0.1"},
        host="127.0.0.1",
    )

    assert visitors._client_ip(request) == "8.8.8.8"


def test_client_ip_falls_back_to_private_ip_when_needed() -> None:
    request = _request({}, host="127.0.0.1")

    assert visitors._client_ip(request) == "127.0.0.1"
