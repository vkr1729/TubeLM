import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock


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
def legacy_channels_json(fixtures_dir):
    return (fixtures_dir / "channels_legacy.json").read_text()


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
