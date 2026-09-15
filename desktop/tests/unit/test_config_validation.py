"""BUG-011/012/019: loud config validation, documented keys, one boolean truth table."""
import pytest

from config import (
    ConfigurationError,
    email_config_attempted,
    load_config,
    require_email_config,
    require_youtube_api_key,
)


FULL_SMTP = {
    "SMTP_SERVER": "smtp.example.com",
    "SMTP_PORT": "587",
    "SMTP_USERNAME": "u",
    "SMTP_PASSWORD": "p",
    "SENDER_EMAIL": "a@example.com",
    "RECIPIENT_EMAIL": "b@example.com",
}


def _clean_env(monkeypatch):
    for key in list(FULL_SMTP) + ["YOUTUBE_API_KEY"]:
        monkeypatch.delenv(key, raising=False)


class TestRequireEmailConfig:
    def test_missing_keys_raise_naming_them(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("SMTP_SERVER", "smtp.example.com")
        cfg = load_config()
        with pytest.raises(ConfigurationError) as excinfo:
            require_email_config(cfg)
        message = str(excinfo.value)
        assert "SMTP_USERNAME" in message
        assert "RECIPIENT_EMAIL" in message

    def test_zero_port_rejected(self, monkeypatch):
        _clean_env(monkeypatch)
        for key, value in FULL_SMTP.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setenv("SMTP_PORT", "0")
        cfg = load_config()
        with pytest.raises(ConfigurationError, match="SMTP_PORT"):
            require_email_config(cfg)

    def test_complete_config_passes(self, monkeypatch):
        _clean_env(monkeypatch)
        for key, value in FULL_SMTP.items():
            monkeypatch.setenv(key, value)
        require_email_config(load_config())  # must not raise


class TestEmailConfigAttempted:
    """RES-002: partial config is fatal-misconfigured; fully-absent may skip."""

    def test_fully_absent_is_not_attempted(self, monkeypatch):
        _clean_env(monkeypatch)
        assert email_config_attempted(load_config()) is False

    def test_any_single_value_counts_as_attempted(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("SMTP_SERVER", "smtp.example.com")
        assert email_config_attempted(load_config()) is True

    def test_port_only_counts_as_attempted(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("SMTP_PORT", "587")
        assert email_config_attempted(load_config()) is True


class TestRequireYoutubeApiKey:
    def test_missing_key_raises(self, monkeypatch):
        _clean_env(monkeypatch)
        with pytest.raises(ConfigurationError, match="YOUTUBE_API_KEY"):
            require_youtube_api_key(load_config())

    def test_present_key_passes(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("YOUTUBE_API_KEY", "key-123")
        require_youtube_api_key(load_config())  # must not raise


class TestSharedBoolTruthTable:
    @pytest.mark.parametrize("word", ["1", "true", "TRUE", "yes", "on", " On "])
    def test_truthy_words(self, monkeypatch, word):
        import paths

        _clean_env(monkeypatch)
        monkeypatch.setenv("COMPRESS_AUDIO", word)
        monkeypatch.delenv("TUBELM_COMPRESS_AUDIO", raising=False)
        assert paths.resolve_bool_env("TUBELM_COMPRESS_AUDIO", "COMPRESS_AUDIO", default=True) is True
        assert paths.resolve_bool_env("TUBELM_COMPRESS_AUDIO", "COMPRESS_AUDIO", default=False) is True

    @pytest.mark.parametrize("word", ["0", "false", "FALSE", "no", "off"])
    def test_falsy_words(self, monkeypatch, word):
        import paths

        _clean_env(monkeypatch)
        monkeypatch.setenv("COMPRESS_AUDIO", word)
        monkeypatch.delenv("TUBELM_COMPRESS_AUDIO", raising=False)
        assert paths.resolve_bool_env("TUBELM_COMPRESS_AUDIO", "COMPRESS_AUDIO", default=True) is False
        assert paths.resolve_bool_env("TUBELM_COMPRESS_AUDIO", "COMPRESS_AUDIO", default=False) is False

    def test_alias_takes_precedence(self, monkeypatch):
        import paths

        _clean_env(monkeypatch)
        monkeypatch.setenv("COMPRESS_AUDIO", "false")
        monkeypatch.setenv("TUBELM_COMPRESS_AUDIO", "true")
        assert paths.resolve_bool_env("TUBELM_COMPRESS_AUDIO", "COMPRESS_AUDIO", default=True) is True

    def test_unset_falls_back_to_default(self, monkeypatch):
        import paths

        _clean_env(monkeypatch)
        monkeypatch.delenv("COMPRESS_AUDIO", raising=False)
        monkeypatch.delenv("TUBELM_COMPRESS_AUDIO", raising=False)
        assert paths.resolve_bool_env("TUBELM_COMPRESS_AUDIO", "COMPRESS_AUDIO", default=True) is True

    def test_config_loader_accepts_on(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.delenv("TUBELM_COMPRESS_AUDIO", raising=False)
        monkeypatch.setenv("COMPRESS_AUDIO", "on")
        assert load_config().compress_audio is True
