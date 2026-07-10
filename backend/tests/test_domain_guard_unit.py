from app.services.domain_guard import domain_from_url


def test_domain_from_url() -> None:
    assert domain_from_url("https://Example.COM/path") == "example.com"
    assert domain_from_url("http://sub.example.org:8080/") == "sub.example.org"
