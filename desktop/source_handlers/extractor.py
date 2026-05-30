import logging

import trafilatura
from bs4 import BeautifulSoup
import requests

logger = logging.getLogger(__name__)


def extract_article_text(url: str, fallback_html: str = "") -> str:
    downloaded = trafilatura.fetch_url(url) if url else None
    if not downloaded:
        downloaded = fallback_html
    if not downloaded:
        return ""

    result = trafilatura.extract(
        downloaded,
        include_comments=False,
        include_tables=True,
        include_links=True,
        output_format="txt",
        favor_precision=True,
    )
    return result or ""


def extract_metadata(url: str) -> dict:
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return {}
    metadata = trafilatura.extract_metadata(downloaded)
    if not metadata:
        return {}
    return {
        "title": metadata.title or "",
        "author": metadata.author or "",
        "date": metadata.date or "",
        "description": metadata.description or "",
    }


def extract_with_beautifulsoup(url: str) -> str:
    resp = requests.get(url, timeout=15, headers={"User-Agent": "TubeLM/2.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "iframe"]):
        tag.decompose()

    article = (
        soup.find("article")
        or soup.find("main")
        or soup.find(class_=["post-content", "article-body", "entry-content"])
        or soup.find("body")
    )
    return article.get_text(separator="\n", strip=True) if article else ""


def extract_clean_text(url: str = "", fallback_html: str = "") -> str:
    text = extract_article_text(url, fallback_html=fallback_html)
    if text and len(text) > 100:
        return text
    try:
        if url:
            return extract_with_beautifulsoup(url)
    except Exception:
        logger.exception("BS4 fallback extraction failed for %s", url)
    return text or ""


MAX_SOURCE_TEXT_LENGTH = 500_000


def truncate_for_notebooklm(text: str) -> str:
    if len(text) > MAX_SOURCE_TEXT_LENGTH:
        logger.warning(
            "Text truncated from %d to %d chars for NotebookLM limit.",
            len(text), MAX_SOURCE_TEXT_LENGTH,
        )
        return text[:MAX_SOURCE_TEXT_LENGTH]
    return text
