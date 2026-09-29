def test_ssl_verify_can_be_disabled() -> None:
    from app.integrations.max.http import ssl_verify

    assert ssl_verify("deploy/certs/russian_trusted_root_ca.pem", verify_ssl=False) is False
    assert ssl_verify("", verify_ssl=True) is True
