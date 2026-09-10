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


def extract_with_crawler_headers(url: str, timeout: int = 10) -> str:
    """Extract article text by presenting Googlebot / Google News crawler headers."""
    if not url:
        return ""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        "Referer": "https://news.google.com/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        html = resp.text
        extracted = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            include_links=True,
            output_format="txt",
            favor_precision=True,
        )
        if extracted and len(extracted) > 250:
            return extracted

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "iframe"]):
            tag.decompose()
        article = (
            soup.find("article")
            or soup.find("main")
            or soup.find(class_=["post-content", "article-body", "entry-content"])
            or soup.find("body")
        )
        if article:
            text = article.get_text(separator="\n", strip=True)
            if len(text) > 250:
                return text
    except Exception as exc:
        logger.debug("Crawler header extraction failed for %s: %s", url, exc)
    return ""


def extract_with_jina(url: str, timeout: int = 10) -> str:
    """Extract full article text via Jina Reader API with strict timeout."""
    if not url:
        return ""
    jina_url = f"https://r.jina.ai/{url}"
    headers = {
        "User-Agent": "TubeLM/2.0",
        "Accept": "text/plain, text/markdown",
    }
    try:
        resp = requests.get(jina_url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        content = resp.text.strip()
        if "Markdown Content:" in content:
            content = content.split("Markdown Content:", 1)[1].strip()
        return content
    except Exception as exc:
        logger.warning("Jina paywall extraction failed for %s: %s", url, exc)
        return ""


def extract_with_archive(url: str, timeout: int = 10) -> str:
    """Fallback: retrieve latest snapshot from the Wayback Machine."""
    if not url:
        return ""
    wayback_url = f"https://web.archive.org/web/2/{url}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    try:
        resp = requests.get(wayback_url, headers=headers, timeout=timeout, allow_redirects=True)
        if resp.status_code == 200:
            extracted = trafilatura.extract(resp.text, output_format="txt")
            if extracted and len(extracted) > 250:
                return extracted
    except Exception as exc:
        logger.debug("Archive extraction failed for %s: %s", url, exc)
    return ""


def extract_paywalled_article(url: str, timeout: int = 10) -> str:
    """Multi-tier paywall extractor: Crawler headers -> Jina Reader -> Wayback -> Trafilatura."""
    if not url:
        return ""

    # Tier 1: Googlebot / Crawler headers (instant, zero rate limits)
    text = extract_with_crawler_headers(url, timeout=timeout)
    if text and len(text) > 250:
        logger.info("Paywall successfully bypassed via Crawler headers (%d chars)", len(text))
        return text

    # Tier 2: Jina Reader API
    text = extract_with_jina(url, timeout=timeout)
    if text and len(text) > 250:
        logger.info("Paywall extracted via Jina Reader (%d chars)", len(text))
        return text

    # Tier 3: Web Archive snapshot
    text = extract_with_archive(url, timeout=timeout)
    if text and len(text) > 250:
        logger.info("Paywall extracted via Wayback Machine (%d chars)", len(text))
        return text

    # Tier 4: Fallback to standard extraction
    text = extract_article_text(url)
    return text or ""


def extract_clean_text(url: str = "", fallback_html: str = "", is_paywalled: bool = False) -> str:
    if is_paywalled and url:
        text = extract_paywalled_article(url)
        if text and len(text) > 100:
            return text
    text = extract_article_text(url, fallback_html=fallback_html)
    if text and len(text) > 100:
        return text
    try:
        if url:
            return extract_with_beautifulsoup(url)
    except Exception:
        logger.exception("BS4 fallback extraction failed for %s", url)
    if url and (not text or len(text) <= 100):
        try:
            crawler_text = extract_with_crawler_headers(url)
            if crawler_text and len(crawler_text) > 100:
                return crawler_text
            jina_text = extract_with_jina(url)
            if jina_text and len(jina_text) > 100:
                return jina_text
        except Exception:
            pass
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
