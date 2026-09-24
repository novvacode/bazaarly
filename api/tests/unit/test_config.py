import pytest

from app.config import Settings


def test_production_requires_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("JWT_SECRET", "RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ValueError, match="JWT_SECRET") as exc:
        Settings(app_env="production", _env_file=None)  # type: ignore[call-arg]
    assert "RAZORPAY_KEY_SECRET is required" in str(exc.value)


def test_local_defaults_are_accepted() -> None:
    s = Settings(app_env="local", _env_file=None)  # type: ignore[call-arg]
    assert s.cors_origin_list == ["http://localhost:3000"]
    assert not s.is_production
