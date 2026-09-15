"""BUG-003: SMTP sends must be time-bounded so one hung MTA cannot stall the run."""
from types import SimpleNamespace
from unittest.mock import patch

from email_service import _send_message, SMTP_TIMEOUT_SECONDS


def _cfg(**overrides):
    base = dict(
        smtp_server="smtp.example.com",
        smtp_port=587,
        smtp_username="u",
        smtp_password="p",
        sender_email="a@example.com",
        recipient_email="b@example.com",
        use_ssl=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_send_message_starttls_passes_timeout():
    from email.mime.multipart import MIMEMultipart

    with patch("email_service.smtplib.SMTP") as mock_smtp:
        _send_message(MIMEMultipart(), _cfg())
    _, kwargs = mock_smtp.call_args
    assert kwargs["timeout"] == SMTP_TIMEOUT_SECONDS
    server = mock_smtp.return_value.__enter__.return_value
    server.starttls.assert_called_once()
    server.login.assert_called_once_with("u", "p")
    server.sendmail.assert_called_once()
    assert server.sendmail.call_args[0][1] == "b@example.com"


def test_send_message_ssl_passes_timeout():
    from email.mime.multipart import MIMEMultipart

    with patch("email_service.smtplib.SMTP_SSL") as mock_smtp_ssl:
        _send_message(MIMEMultipart(), _cfg(smtp_port=465, use_ssl=True))
    _, kwargs = mock_smtp_ssl.call_args
    assert kwargs["timeout"] == SMTP_TIMEOUT_SECONDS
    server = mock_smtp_ssl.return_value.__enter__.return_value
    server.login.assert_called_once_with("u", "p")
    server.sendmail.assert_called_once()
