import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture(autouse=True)
def prevent_gh_pages_deploy_in_tests(monkeypatch):
    """Safety guard: prevent any automated test from accidentally pushing to GitHub Pages."""
    import web_reader
    monkeypatch.setattr(web_reader, "deploy_to_gh_pages", lambda *args, **kwargs: True)


@pytest.fixture(autouse=True)
def prevent_email_sending_in_tests(monkeypatch, request):
    """Safety guard: prevent any automated test from sending live emails."""
    mod_name = request.module.__name__ if hasattr(request, "module") and request.module else ""
    if "test_email_service" not in mod_name:
        try:
            import email_service
            monkeypatch.setattr(email_service, "send_channel_email", lambda *args, **kwargs: None)
            monkeypatch.setattr(email_service, "send_top10_email", lambda *args, **kwargs: None)
            monkeypatch.setattr(email_service, "send_artifact_completion_email", lambda *args, **kwargs: None)
            monkeypatch.setattr(email_service, "verify_smtp_connection", lambda *args, **kwargs: None)
        except Exception:
            pass
        try:
            import main
            monkeypatch.setattr(main, "send_channel_email", lambda *args, **kwargs: None, raising=False)
        except Exception:
            pass
        monkeypatch.setenv("SKIP_EMAIL", "1")


@pytest.fixture
def fixtures_dir():
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def article_html(fixtures_dir):
    return (fixtures_dir / "webpage_article.html").read_text()


@pytest.fixture
def index_html(fixtures_dir):
    return (fixtures_dir / "webpage_index.html").read_text()


@pytest.fixture
def js_heavy_html(fixtures_dir):
    return (fixtures_dir / "webpage_js_heavy.html").read_text()


@pytest.fixture
def minimal_html(fixtures_dir):
    return (fixtures_dir / "webpage_minimal.html").read_text()


@pytest.fixture
def rss_techblog_xml(fixtures_dir):
    return (fixtures_dir / "rss_techblog.xml").read_text()


@pytest.fixture
def rss_atom_xml(fixtures_dir):
    return (fixtures_dir / "rss_atom.xml").read_text()


@pytest.fixture
def rss_malformed_xml(fixtures_dir):
    return (fixtures_dir / "rss_malformed.xml").read_text()


@pytest.fixture
def mock_notebooklm_client():
    client = AsyncMock()
    client.notebooks.create.return_value = MagicMock(id="nb_test_001")
    client.notebooks.get_share_url.return_value = "https://notebooklm.google.com/notebook/nb_test_001"
    client.sources.add_url.return_value = MagicMock(id="src_url_001")
    client.sources.add_text.return_value = MagicMock(id="src_text_001")
    client.sources.wait_for_sources.return_value = []
    client.chat.ask.return_value = MagicMock(answer="AI-generated summary...")
    return client
