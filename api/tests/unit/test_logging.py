from app.core.logging import _scrub, mask_phone


def test_mask_phone_keeps_last_four() -> None:
    assert mask_phone("+919876543210") == "******3210"
    assert mask_phone("12") == "****"


def test_scrub_redacts_secrets_and_masks_phones() -> None:
    event = _scrub(
        None,
        "info",
        {
            "event": "customer +91 98765 43210 ordered",
            "password": "hunter2",
            "access_token": "eyJ...",
            "razorpay_signature": "abc",
            "webhook_secret": "s",
            "customer_phone": "+919876543210",
            "order_id": "123",
        },
    )
    assert event["password"] == "[redacted]"
    assert event["access_token"] == "[redacted]"
    assert event["razorpay_signature"] == "[redacted]"
    assert event["webhook_secret"] == "[redacted]"
    assert event["customer_phone"] == "******3210"
    assert event["order_id"] == "123"
    assert "98765" not in event["event"]
    assert "3210" in event["event"]
