from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from notebooklm import NotebookLMClient


@dataclass
class SourceItem:
    title: str
    url: str
    published: str
    description: str = ""
    extracted_text: str = ""
    source_id: str = ""


class BaseSourceHandler(ABC):

    @property
    @abstractmethod
    def source_type(self) -> str:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def discover(self, since_dt: datetime, seen_urls: set[str] | None = None) -> list[SourceItem] | None:
        ...

    @abstractmethod
    async def ingest(
        self,
        client: "NotebookLMClient",
        notebook_id: str,
        items: list[SourceItem],
    ) -> list[str]:
        ...

    @abstractmethod
    def state_key(self) -> str:
        ...
