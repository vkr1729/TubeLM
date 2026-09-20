from source_handlers import BaseSourceHandler
from source_handlers.youtube_handler import YouTubeHandler
from source_handlers.rss_handler import GenericRSSHandler
from source_handlers.webpage_handler import WebpageScraperHandler


def _bounded_max_items(value, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return max(1, min(parsed, 50))


def create_handler(source_config: dict, cfg: object = None) -> BaseSourceHandler:
    if not isinstance(source_config, dict):
        raise ValueError("Source config must be a dict.")
    source_type = source_config.get("type", "youtube")
    category = source_config.get("category", "tech")
    if not isinstance(category, str) or not category.strip():
        category = "tech"
    else:
        category = category.strip()
    name = source_config.get("name", "")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Source entry is missing a valid 'name'.")

    if source_type == "youtube":
        channel_id = source_config.get("channel_id", "")
        if not isinstance(channel_id, str) or not channel_id.strip():
            raise ValueError(f"Source {name!r} is missing 'channel_id'.")
        return YouTubeHandler(
            name=name,
            channel_id=channel_id,
            youtube_api_key=getattr(cfg, "youtube_api_key", "") if cfg else "",
            category=category,
        )
    elif source_type == "rss":
        url = source_config.get("url", "")
        if not isinstance(url, str) or not url.strip():
            raise ValueError(f"Source {name!r} is missing 'url'.")
        behind_paywall = source_config.get("behind_paywall", True)
        return GenericRSSHandler(
            name=name,
            url=url,
            force_text_extraction=source_config.get("force_text_extraction", False),
            behind_paywall=behind_paywall,
            max_items=_bounded_max_items(source_config.get("max_items"), 15),
            category=category,
        )
    elif source_type == "webpage":
        url = source_config.get("url", "")
        if not isinstance(url, str) or not url.strip():
            raise ValueError(f"Source {name!r} is missing 'url'.")
        link_selector = source_config.get("link_selector", "")
        if not isinstance(link_selector, str):
            link_selector = ""
        return WebpageScraperHandler(
            name=name,
            url=url,
            is_index_page=source_config.get("is_index_page", False),
            link_selector=link_selector,
            max_items=_bounded_max_items(source_config.get("max_items"), 10),
            category=category,
        )
    else:
        raise ValueError(f"Unknown source type: {source_type}")
