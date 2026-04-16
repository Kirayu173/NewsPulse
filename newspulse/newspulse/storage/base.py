# coding=utf-8
"""
Storage backend base classes and shared news data models.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class NewsItem:
    """Single hotlist news item."""

    title: str
    source_id: str
    source_name: str = ""
    rank: int = 0
    url: str = ""
    mobile_url: str = ""
    crawl_time: str = ""
    ranks: List[int] = field(default_factory=list)
    first_time: str = ""
    last_time: str = ""
    count: int = 1
    rank_timeline: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "rank": self.rank,
            "url": self.url,
            "mobile_url": self.mobile_url,
            "crawl_time": self.crawl_time,
            "ranks": self.ranks,
            "first_time": self.first_time,
            "last_time": self.last_time,
            "count": self.count,
            "rank_timeline": self.rank_timeline,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NewsItem":
        return cls(
            title=data.get("title", ""),
            source_id=data.get("source_id", ""),
            source_name=data.get("source_name", ""),
            rank=data.get("rank", 0),
            url=data.get("url", ""),
            mobile_url=data.get("mobile_url", ""),
            crawl_time=data.get("crawl_time", ""),
            ranks=data.get("ranks", []),
            first_time=data.get("first_time", ""),
            last_time=data.get("last_time", ""),
            count=data.get("count", 1),
            rank_timeline=data.get("rank_timeline", []),
        )


@dataclass
class NewsData:
    """Collection of hotlist crawl data grouped by source."""

    date: str
    crawl_time: str
    items: Dict[str, List[NewsItem]]
    id_to_name: Dict[str, str] = field(default_factory=dict)
    failed_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        items_dict = {}
        for source_id, news_list in self.items.items():
            items_dict[source_id] = [item.to_dict() for item in news_list]

        return {
            "date": self.date,
            "crawl_time": self.crawl_time,
            "items": items_dict,
            "id_to_name": self.id_to_name,
            "failed_ids": self.failed_ids,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NewsData":
        items = {}
        items_data = data.get("items", {})
        for source_id, news_list in items_data.items():
            items[source_id] = [NewsItem.from_dict(item) for item in news_list]

        return cls(
            date=data.get("date", ""),
            crawl_time=data.get("crawl_time", ""),
            items=items,
            id_to_name=data.get("id_to_name", {}),
            failed_ids=data.get("failed_ids", []),
        )

    def get_total_count(self) -> int:
        return sum(len(news_list) for news_list in self.items.values())

    def merge_with(self, other: "NewsData") -> "NewsData":
        merged_items = {}

        for source_id, news_list in self.items.items():
            merged_items[source_id] = {item.title: item for item in news_list}

        for source_id, news_list in other.items.items():
            if source_id not in merged_items:
                merged_items[source_id] = {}

            for item in news_list:
                if item.title in merged_items[source_id]:
                    existing = merged_items[source_id][item.title]
                    existing_ranks = set(existing.ranks) if existing.ranks else set()
                    new_ranks = set(item.ranks) if item.ranks else set()
                    existing.ranks = sorted(existing_ranks | new_ranks)

                    if item.first_time and (not existing.first_time or item.first_time < existing.first_time):
                        existing.first_time = item.first_time
                    if item.last_time and (not existing.last_time or item.last_time > existing.last_time):
                        existing.last_time = item.last_time

                    existing.count += 1
                    if not existing.url and item.url:
                        existing.url = item.url
                    if not existing.mobile_url and item.mobile_url:
                        existing.mobile_url = item.mobile_url
                else:
                    merged_items[source_id][item.title] = item

        final_items = {
            source_id: list(items_dict.values())
            for source_id, items_dict in merged_items.items()
        }
        merged_id_to_name = {**self.id_to_name, **other.id_to_name}
        merged_failed_ids = list(set(self.failed_ids + other.failed_ids))

        return NewsData(
            date=self.date or other.date,
            crawl_time=other.crawl_time,
            items=final_items,
            id_to_name=merged_id_to_name,
            failed_ids=merged_failed_ids,
        )


class StorageBackend(ABC):
    """Abstract storage backend used by NewsPulse."""

    @abstractmethod
    def save_news_data(self, data: NewsData) -> bool:
        pass

    @abstractmethod
    def get_today_all_data(self, date: Optional[str] = None) -> Optional[NewsData]:
        pass

    @abstractmethod
    def get_latest_crawl_data(self, date: Optional[str] = None) -> Optional[NewsData]:
        pass

    @abstractmethod
    def detect_new_titles(self, current_data: NewsData) -> Dict[str, Dict]:
        pass

    @abstractmethod
    def save_txt_snapshot(self, data: NewsData) -> Optional[str]:
        pass

    @abstractmethod
    def save_html_report(self, html_content: str, filename: str) -> Optional[str]:
        pass

    @abstractmethod
    def is_first_crawl_today(self, date: Optional[str] = None) -> bool:
        pass

    @abstractmethod
    def cleanup(self) -> None:
        pass

    @abstractmethod
    def cleanup_old_data(self, retention_days: int) -> int:
        pass

    @property
    @abstractmethod
    def backend_name(self) -> str:
        pass

    @property
    @abstractmethod
    def supports_txt(self) -> bool:
        pass

    def has_period_executed(self, date_str: str, period_key: str, action: str) -> bool:
        return False

    def record_period_execution(self, date_str: str, period_key: str, action: str) -> bool:
        return False

    def begin_batch(self) -> None:
        pass

    def end_batch(self) -> None:
        pass

    def get_active_ai_filter_tags(self, date: Optional[str] = None, interests_file: str = "ai_interests.txt") -> List[Dict]:
        return []

    def get_latest_prompt_hash(self, date: Optional[str] = None, interests_file: str = "ai_interests.txt") -> Optional[str]:
        return None

    def get_latest_ai_filter_tag_version(self, date: Optional[str] = None) -> int:
        return 0

    def deprecate_all_ai_filter_tags(self, date: Optional[str] = None, interests_file: str = "ai_interests.txt") -> int:
        return 0

    def save_ai_filter_tags(self, tags: List[Dict], version: int, prompt_hash: str, date: Optional[str] = None, interests_file: str = "ai_interests.txt") -> int:
        return 0

    def save_ai_filter_results(self, results: List[Dict], date: Optional[str] = None) -> int:
        return 0

    def get_active_ai_filter_results(self, date: Optional[str] = None, interests_file: str = "ai_interests.txt") -> List[Dict]:
        return []

    def deprecate_specific_ai_filter_tags(self, tag_ids: List[int], date: Optional[str] = None) -> int:
        return 0

    def update_ai_filter_tags_hash(self, interests_file: str, new_hash: str, date: Optional[str] = None) -> int:
        return 0

    def update_ai_filter_tag_descriptions(self, tag_updates: List[Dict], date: Optional[str] = None, interests_file: str = "ai_interests.txt") -> int:
        return 0

    def update_ai_filter_tag_priorities(self, tag_priorities: List[Dict], date: Optional[str] = None, interests_file: str = "ai_interests.txt") -> int:
        return 0

    def save_analyzed_news(self, news_ids: List[str], source_type: str, interests_file: str, prompt_hash: str, matched_ids: Set[str], date: Optional[str] = None) -> int:
        return 0

    def get_analyzed_news_ids(self, source_type: str = "hotlist", date: Optional[str] = None, interests_file: str = "ai_interests.txt") -> Set[str]:
        return set()

    def clear_analyzed_news(self, date: Optional[str] = None, interests_file: str = "ai_interests.txt") -> int:
        return 0

    def clear_unmatched_analyzed_news(self, date: Optional[str] = None, interests_file: str = "ai_interests.txt") -> int:
        return 0

    def get_all_news_ids(self, date: Optional[str] = None) -> List[Dict]:
        return []


def convert_crawl_results_to_news_data(
    results: Dict[str, Dict],
    id_to_name: Dict[str, str],
    failed_ids: List[str],
    crawl_time: str,
    crawl_date: str,
) -> NewsData:
    """Convert crawler output into ``NewsData``."""
    items = {}

    for source_id, titles_data in results.items():
        source_name = id_to_name.get(source_id, source_id)
        news_list = []

        for title, data in titles_data.items():
            ranks = data.get("ranks", [])
            url = data.get("url", "")
            mobile_url = data.get("mobileUrl", "")
            rank = ranks[0] if ranks else 99

            news_list.append(
                NewsItem(
                    title=title,
                    source_id=source_id,
                    source_name=source_name,
                    rank=rank,
                    url=url,
                    mobile_url=mobile_url,
                    crawl_time=crawl_time,
                    ranks=ranks,
                    first_time=crawl_time,
                    last_time=crawl_time,
                    count=1,
                )
            )

        items[source_id] = news_list

    return NewsData(
        date=crawl_date,
        crawl_time=crawl_time,
        items=items,
        id_to_name=id_to_name,
        failed_ids=failed_ids,
    )
