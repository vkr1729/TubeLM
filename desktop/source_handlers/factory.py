from source_handlers import BaseSourceHandler
from source_handlers.youtube_handler import YouTubeHandler
from source_handlers.rss_handler import GenericRSSHandler
from source_handlers.webpage_handler import WebpageScraperHandler


def create_handler(source_config: dict, cfg: object = None) -> BaseSourceHandler:
    source_type = source_config.get("type", "youtube")

    if source_type == "youtube":
        return YouTubeHandler(
            name=source_config["name"],
            channel_id=source_config["channel_id"],
            youtube_api_key=getattr(cfg, "youtube_api_key", "") if cfg else "",
        )
    elif source_type == "rss":
        return GenericRSSHandler(
            name=source_config["name"],
            url=source_config["url"],
            force_text_extraction=source_config.get("force_text_extraction", False),
            max_items=source_config.get("max_items", 15),
        )
    elif source_type == "webpage":
        return WebpageScraperHandler(
            name=source_config["name"],
            url=source_config["url"],
            is_index_page=source_config.get("is_index_page", False),
            link_selector=source_config.get("link_selector", ""),
            max_items=source_config.get("max_items", 10),
        )
    else:
        raise ValueError(f"Unknown source type: {source_type}")
