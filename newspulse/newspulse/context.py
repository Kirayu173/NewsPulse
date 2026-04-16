# coding=utf-8
"""Application context helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from newspulse.ai import AITranslator
from newspulse.ai.filter import AIFilter, AIFilterResult
from newspulse.core import (
    Scheduler,
    count_word_frequency,
    detect_latest_new_titles,
    load_frequency_words,
    matches_word_groups,
    read_all_today_titles,
)
from newspulse.notification import NotificationDispatcher, split_content_into_batches
from newspulse.report import generate_html_report, prepare_report_data, render_html_content
from newspulse.storage import get_storage_manager
from newspulse.utils.time import (
    DEFAULT_TIMEZONE,
    convert_time_for_display,
    format_date_folder,
    format_time_filename,
    get_configured_time,
    get_current_time_display,
)


class AppContext:
    """Thin runtime facade around config, storage and report helpers."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._storage_manager = None
        self._scheduler = None

    @property
    def timezone(self) -> str:
        return self.config.get("TIMEZONE", DEFAULT_TIMEZONE)

    @property
    def rank_threshold(self) -> int:
        return self.config.get("RANK_THRESHOLD", 50)

    @property
    def weight_config(self) -> Dict[str, Any]:
        return self.config.get("WEIGHT_CONFIG", {})

    @property
    def platforms(self) -> List[Dict[str, Any]]:
        return self.config.get("PLATFORMS", [])

    @property
    def platform_ids(self) -> List[str]:
        return [platform.get("id", "") for platform in self.platforms if platform.get("id")]

    @property
    def display_mode(self) -> str:
        return self.config.get("DISPLAY_MODE", "keyword")

    @property
    def show_new_section(self) -> bool:
        return self.config.get("DISPLAY", {}).get("REGIONS", {}).get("NEW_ITEMS", True)

    @property
    def region_order(self) -> List[str]:
        return self.config.get(
            "DISPLAY", {}
        ).get("REGION_ORDER", ["hotlist", "new_items", "standalone", "ai_analysis"])

    @property
    def filter_method(self) -> str:
        return self.config.get("FILTER", {}).get("METHOD", "keyword")

    @property
    def ai_priority_sort_enabled(self) -> bool:
        return self.config.get("FILTER", {}).get("PRIORITY_SORT_ENABLED", False)

    @property
    def ai_filter_config(self) -> Dict[str, Any]:
        return self.config.get("AI_FILTER", {})

    @property
    def ai_analysis_model_config(self) -> Dict[str, Any]:
        return self.config.get("AI_ANALYSIS_MODEL", self.config.get("AI", {}))

    @property
    def ai_translation_model_config(self) -> Dict[str, Any]:
        return self.config.get("AI_TRANSLATION_MODEL", self.config.get("AI", {}))

    @property
    def ai_filter_model_config(self) -> Dict[str, Any]:
        return self.config.get("AI_FILTER_MODEL", self.config.get("AI", {}))

    @property
    def ai_filter_enabled(self) -> bool:
        return self.filter_method == "ai"

    @property
    def config_root(self) -> Path:
        config_root = self.config.get("_PATHS", {}).get("CONFIG_ROOT")
        return Path(config_root) if config_root else Path("config")

    def get_time(self) -> datetime:
        return get_configured_time(self.timezone)

    def format_date(self) -> str:
        return format_date_folder(timezone=self.timezone)

    def format_time(self) -> str:
        return format_time_filename(self.timezone)

    def get_time_display(self) -> str:
        return get_current_time_display(self.timezone)

    @staticmethod
    def convert_time_display(time_str: str) -> str:
        return convert_time_for_display(time_str)

    def get_storage_manager(self):
        if self._storage_manager is None:
            self._storage_manager = get_storage_manager(
                backend_type=self.config.get("STORAGE", {}).get("BACKEND", "local"),
                data_dir=str(self.get_data_dir()),
                enable_txt=self.config.get("STORAGE", {}).get("FORMATS", {}).get("TXT", True),
                enable_html=self.config.get("STORAGE", {}).get("FORMATS", {}).get("HTML", True),
                local_retention_days=self.config.get("STORAGE", {}).get("LOCAL", {}).get("RETENTION_DAYS", 0),
                timezone=self.timezone,
            )
        return self._storage_manager

    def get_data_dir(self) -> Path:
        storage_config = self.config.get("STORAGE", {})
        local_config = storage_config.get("LOCAL", {})
        return Path(local_config.get("DATA_DIR", "output"))

    def get_output_path(self, subfolder: str, filename: str) -> str:
        output_dir = self.get_data_dir() / subfolder / self.format_date()
        output_dir.mkdir(parents=True, exist_ok=True)
        return str(output_dir / filename)

    def read_today_titles(self, platform_ids: Optional[List[str]] = None, quiet: bool = False) -> Tuple[Dict, Dict, Dict]:
        return read_all_today_titles(self.get_storage_manager(), platform_ids, quiet=quiet)

    def detect_new_titles(self, platform_ids: Optional[List[str]] = None, quiet: bool = False) -> Dict:
        return detect_latest_new_titles(self.get_storage_manager(), platform_ids, quiet=quiet)

    def is_first_crawl(self) -> bool:
        return self.get_storage_manager().is_first_crawl_today()

    def load_frequency_words(self, frequency_file: Optional[str] = None) -> Tuple[List[Dict], List[str], List[str]]:
        return load_frequency_words(frequency_file, config_root=self.config_root)

    def matches_word_groups(
        self,
        title: str,
        word_groups: List[Dict],
        filter_words: List[str],
        global_filters: Optional[List[str]] = None,
    ) -> bool:
        return matches_word_groups(title, word_groups, filter_words, global_filters)

    def count_frequency(
        self,
        results: Dict,
        word_groups: List[Dict],
        filter_words: List[str],
        id_to_name: Dict,
        title_info: Optional[Dict] = None,
        new_titles: Optional[Dict] = None,
        mode: str = "daily",
        global_filters: Optional[List[str]] = None,
        quiet: bool = False,
    ) -> Tuple[List[Dict], int]:
        return count_word_frequency(
            results=results,
            word_groups=word_groups,
            filter_words=filter_words,
            id_to_name=id_to_name,
            title_info=title_info,
            rank_threshold=self.rank_threshold,
            new_titles=new_titles,
            mode=mode,
            global_filters=global_filters,
            weight_config=self.weight_config,
            max_news_per_keyword=self.config.get("MAX_NEWS_PER_KEYWORD", 0),
            sort_by_position_first=self.config.get("SORT_BY_POSITION_FIRST", False),
            is_first_crawl_func=self.is_first_crawl,
            convert_time_func=self.convert_time_display,
            quiet=quiet,
        )

    def prepare_report(
        self,
        stats: List[Dict],
        failed_ids: Optional[List] = None,
        new_titles: Optional[Dict] = None,
        id_to_name: Optional[Dict] = None,
        mode: str = "daily",
        frequency_file: Optional[str] = None,
    ) -> Dict:
        return prepare_report_data(
            stats=stats,
            failed_ids=failed_ids,
            new_titles=new_titles,
            id_to_name=id_to_name,
            mode=mode,
            rank_threshold=self.rank_threshold,
            matches_word_groups_func=self.matches_word_groups,
            load_frequency_words_func=lambda: self.load_frequency_words(frequency_file),
            show_new_section=self.show_new_section,
        )

    def generate_html(
        self,
        stats: List[Dict],
        total_titles: int,
        failed_ids: Optional[List] = None,
        new_titles: Optional[Dict] = None,
        id_to_name: Optional[Dict] = None,
        mode: str = "daily",
        update_info: Optional[Dict] = None,
        ai_analysis: Optional[Any] = None,
        standalone_data: Optional[Dict] = None,
        frequency_file: Optional[str] = None,
    ) -> str:
        return generate_html_report(
            stats=stats,
            total_titles=total_titles,
            failed_ids=failed_ids,
            new_titles=new_titles,
            id_to_name=id_to_name,
            mode=mode,
            update_info=update_info,
            rank_threshold=self.rank_threshold,
            output_dir=str(self.get_data_dir()),
            date_folder=self.format_date(),
            time_filename=self.format_time(),
            render_html_func=lambda *args, **kwargs: self.render_html(
                *args,
                ai_analysis=ai_analysis,
                standalone_data=standalone_data,
                **kwargs,
            ),
            matches_word_groups_func=self.matches_word_groups,
            load_frequency_words_func=lambda: self.load_frequency_words(frequency_file),
        )

    def render_html(
        self,
        report_data: Dict,
        total_titles: int,
        mode: str = "daily",
        update_info: Optional[Dict] = None,
        ai_analysis: Optional[Any] = None,
        standalone_data: Optional[Dict] = None,
    ) -> str:
        return render_html_content(
            report_data=report_data,
            total_titles=total_titles,
            mode=mode,
            update_info=update_info,
            region_order=self.region_order,
            get_time_func=self.get_time,
            display_mode=self.display_mode,
            ai_analysis=ai_analysis,
            show_new_section=self.show_new_section,
            standalone_data=standalone_data,
        )

    def split_content(
        self,
        report_data: Dict,
        format_type: str,
        update_info: Optional[Dict] = None,
        max_bytes: Optional[int] = None,
        mode: str = "daily",
        ai_content: Optional[str] = None,
        standalone_data: Optional[Dict] = None,
        ai_stats: Optional[Dict] = None,
        report_type: str = "热点分析报告",
    ) -> List[str]:
        return split_content_into_batches(
            report_data=report_data,
            format_type=format_type,
            update_info=update_info,
            max_bytes=max_bytes,
            mode=mode,
            batch_sizes={"default": self.config.get("MESSAGE_BATCH_SIZE", 4000)},
            region_order=self.region_order,
            get_time_func=self.get_time,
            timezone=self.timezone,
            display_mode=self.display_mode,
            ai_content=ai_content,
            standalone_data=standalone_data,
            rank_threshold=self.rank_threshold,
            ai_stats=ai_stats,
            report_type=report_type,
            show_new_section=self.show_new_section,
        )

    def create_notification_dispatcher(self) -> NotificationDispatcher:
        translator = None
        translation_config = self.config.get("AI_TRANSLATION", {})
        if translation_config.get("ENABLED", False):
            translator = AITranslator(translation_config, self.ai_translation_model_config)

        return NotificationDispatcher(
            config=self.config,
            get_time_func=self.get_time,
            split_content_func=self.split_content,
            translator=translator,
        )

    def create_scheduler(self) -> Scheduler:
        if self._scheduler is None:
            self._scheduler = Scheduler(
                schedule_config=self.config.get("SCHEDULE", {}),
                timeline_data=self.config.get("_TIMELINE_DATA", {}),
                storage_backend=self.get_storage_manager(),
                get_time_func=self.get_time,
                fallback_report_mode=self.config.get("REPORT_MODE", "current"),
            )
        return self._scheduler

    @staticmethod
    def _with_ordered_priorities(tags: List[Dict], start_priority: int = 1) -> List[Dict]:
        normalized: List[Dict] = []
        priority = start_priority
        for tag_data in tags:
            if not isinstance(tag_data, dict):
                continue
            tag_name = str(tag_data.get("tag", "")).strip()
            if not tag_name:
                continue
            item = dict(tag_data)
            item["tag"] = tag_name
            item["priority"] = priority
            normalized.append(item)
            priority += 1
        return normalized

    def run_ai_filter(self, interests_file: Optional[str] = None) -> Optional[AIFilterResult]:
        if not self.ai_filter_enabled:
            return None

        filter_config = self.ai_filter_config
        ai_filter = AIFilter(
            self.ai_filter_model_config,
            filter_config,
            self.get_time,
            debug=self.config.get("DEBUG", False),
            config_root=self.config_root,
        )
        storage = self.get_storage_manager()

        configured_interests = interests_file or filter_config.get("INTERESTS_FILE")
        effective_interests_file = configured_interests or "ai_interests.txt"
        interests_content = ai_filter.load_interests_content(configured_interests)
        if not interests_content:
            return AIFilterResult(success=False, error="未找到可用的 AI 兴趣描述文件")

        current_hash = ai_filter.compute_interests_hash(interests_content, effective_interests_file)
        storage.begin_batch()
        try:
            active_tags = storage.get_active_ai_filter_tags(interests_file=effective_interests_file)
            latest_hash = storage.get_latest_prompt_hash(interests_file=effective_interests_file)

            if not active_tags or latest_hash != current_hash:
                if active_tags:
                    print("[AI筛选] 兴趣配置已变化，重新生成标签并全量重跑")
                    storage.deprecate_all_ai_filter_tags(interests_file=effective_interests_file)
                    storage.clear_analyzed_news(interests_file=effective_interests_file)

                extracted_tags = ai_filter.extract_tags(interests_content)
                ordered_tags = self._with_ordered_priorities(extracted_tags)
                if not ordered_tags:
                    return AIFilterResult(success=False, error="AI 未能提取有效标签")

                version = storage.get_latest_ai_filter_tag_version() + 1
                saved = storage.save_ai_filter_tags(
                    ordered_tags,
                    version,
                    current_hash,
                    interests_file=effective_interests_file,
                )
                if saved <= 0:
                    return AIFilterResult(success=False, error="标签保存失败")
                active_tags = storage.get_active_ai_filter_tags(interests_file=effective_interests_file)

            all_news = storage.get_all_news_ids()
            analyzed_news = storage.get_analyzed_news_ids("hotlist", interests_file=effective_interests_file)
            pending_news = [item for item in all_news if item["id"] not in analyzed_news]

            print(
                f"[AI筛选] 热榜: 总计 {len(all_news)} 条, 已分析跳过 {len(analyzed_news)} 条, 本次发送 AI 分析 {len(pending_news)} 条"
            )

            batch_size = filter_config.get("BATCH_SIZE", 200)
            batch_interval = filter_config.get("BATCH_INTERVAL", 5)
            total_results: List[Dict[str, Any]] = []

            for batch_index, start in enumerate(range(0, len(pending_news), batch_size), start=1):
                if batch_index > 1 and batch_interval > 0:
                    import time

                    print(f"[AI筛选] 批次间隔等待 {batch_interval} 秒...")
                    time.sleep(batch_interval)

                batch = pending_news[start : start + batch_size]
                batch_payload = [
                    {"id": item["id"], "title": item["title"], "source": item.get("source_name", "")}
                    for item in batch
                ]
                batch_results = ai_filter.classify_batch(batch_payload, active_tags, interests_content)
                for result in batch_results:
                    result["source_type"] = "hotlist"
                total_results.extend(batch_results)
                print(f"[AI筛选] 热榜批次 {batch_index}: {len(batch)} 条 -> {len(batch_results)} 条匹配")

            if total_results:
                saved = storage.save_ai_filter_results(total_results)
                print(f"[AI筛选] 已保存 {saved} 条分类结果")

            if pending_news:
                matched_ids = {result["news_item_id"] for result in total_results}
                storage.save_analyzed_news(
                    [item["id"] for item in pending_news],
                    "hotlist",
                    effective_interests_file,
                    current_hash,
                    matched_ids,
                )

            active_results = storage.get_active_ai_filter_results(interests_file=effective_interests_file)
            return self._build_filter_result(active_results, active_tags, len(pending_news))
        finally:
            storage.end_batch()

    def _build_filter_result(
        self,
        raw_results: List[Dict],
        tags: List[Dict],
        total_processed: int,
    ) -> AIFilterResult:
        tag_priority_map = {}
        for index, tag in enumerate(tags, start=1):
            tag_name = str(tag.get("tag", "")).strip() if isinstance(tag, dict) else ""
            if not tag_name:
                continue
            try:
                tag_priority_map[tag_name] = int(tag.get("priority", index))
            except (TypeError, ValueError):
                tag_priority_map[tag_name] = index

        tag_groups: Dict[str, Dict[str, Any]] = {}
        seen_titles: Dict[str, set] = {}

        for result in raw_results:
            tag_name = result["tag"]
            if tag_name not in tag_groups:
                raw_priority = result.get("tag_priority", tag_priority_map.get(tag_name, 9999))
                try:
                    tag_position = int(raw_priority)
                except (TypeError, ValueError):
                    tag_position = 9999
                tag_groups[tag_name] = {
                    "tag": tag_name,
                    "description": result.get("tag_description", ""),
                    "position": tag_position,
                    "count": 0,
                    "items": [],
                }
                seen_titles[tag_name] = set()

            title = result.get("title", "")
            if not title or title in seen_titles[tag_name]:
                continue
            seen_titles[tag_name].add(title)

            tag_groups[tag_name]["items"].append(
                {
                    "title": title,
                    "source_id": result.get("source_id", ""),
                    "source_name": result.get("source_name", ""),
                    "url": result.get("url", ""),
                    "mobile_url": result.get("mobile_url", ""),
                    "rank": result.get("rank", 0),
                    "ranks": result.get("ranks", []),
                    "first_time": result.get("first_time", ""),
                    "last_time": result.get("last_time", ""),
                    "count": result.get("count", 1),
                    "relevance_score": result.get("relevance_score", 0),
                    "source_type": "hotlist",
                }
            )
            tag_groups[tag_name]["count"] += 1

        if self.ai_priority_sort_enabled:
            sorted_tags = sorted(
                tag_groups.values(),
                key=lambda item: (item.get("position", 9999), -item["count"], item["tag"]),
            )
        else:
            sorted_tags = sorted(
                tag_groups.values(),
                key=lambda item: (-item["count"], item.get("position", 9999), item["tag"]),
            )

        total_matched = sum(tag["count"] for tag in sorted_tags)
        return AIFilterResult(
            tags=sorted_tags,
            total_matched=total_matched,
            total_processed=total_processed,
            success=True,
        )

    def convert_ai_filter_to_report_data(
        self,
        ai_filter_result: AIFilterResult,
        mode: str = "daily",
        new_titles: Optional[Dict] = None,
    ) -> List[Dict]:
        hotlist_stats: List[Dict[str, Any]] = []
        max_news = self.config.get("MAX_NEWS_PER_KEYWORD", 0)
        min_score = self.ai_filter_config.get("MIN_SCORE", 0)

        latest_time = None
        if mode == "current":
            for tag_data in ai_filter_result.tags:
                for item in tag_data.get("items", []):
                    last_time = item.get("last_time", "")
                    if last_time and (latest_time is None or last_time > latest_time):
                        latest_time = last_time
            if latest_time:
                print(f"[AI筛选] current 模式: 最新时间 {latest_time}，仅保留当前在榜内容")

        filtered_count = 0
        for tag_data in ai_filter_result.tags:
            tag_name = tag_data.get("tag", "")
            titles = []

            for item in tag_data.get("items", []):
                if item.get("source_type", "hotlist") != "hotlist":
                    continue

                if mode == "current" and latest_time and item.get("last_time", "") != latest_time:
                    filtered_count += 1
                    continue

                if min_score > 0 and item.get("relevance_score", 0) < min_score:
                    continue

                item_source_id = item.get("source_id", "")
                item_title = item.get("title", "")
                is_new = bool(new_titles and item_source_id in new_titles and item_title in new_titles[item_source_id])
                if mode == "incremental" and not is_new:
                    continue

                first_time = item.get("first_time", "")
                last_time = item.get("last_time", "")
                if first_time and last_time and first_time != last_time:
                    time_display = f"[{convert_time_for_display(first_time)} ~ {convert_time_for_display(last_time)}]"
                elif first_time:
                    time_display = convert_time_for_display(first_time)
                else:
                    time_display = ""

                titles.append(
                    {
                        "title": item_title,
                        "source_name": item.get("source_name", ""),
                        "url": item.get("url", ""),
                        "mobileUrl": item.get("mobile_url", ""),
                        "ranks": item.get("ranks", []),
                        "rank_threshold": self.rank_threshold,
                        "count": item.get("count", 1),
                        "is_new": is_new,
                        "time_display": time_display,
                        "matched_keyword": tag_name,
                    }
                )

            if titles:
                if max_news > 0:
                    titles = titles[:max_news]
                hotlist_stats.append(
                    {
                        "word": tag_name,
                        "count": len(titles),
                        "position": tag_data.get("position", 9999),
                        "titles": titles,
                    }
                )

        if mode == "current" and filtered_count > 0:
            kept_count = sum(stat["count"] for stat in hotlist_stats)
            print(f"[AI筛选] current 模式: 过滤 {filtered_count} 条已下榜新闻，保留 {kept_count} 条当前在榜内容")

        if min_score > 0:
            kept_count = sum(stat["count"] for stat in hotlist_stats)
            print(f"[AI筛选] 分数过滤: min_score={min_score}，保留 {kept_count} 条内容")

        if self.ai_priority_sort_enabled:
            hotlist_stats.sort(key=lambda item: (item.get("position", 9999), -item["count"], item["word"]))
        else:
            hotlist_stats.sort(key=lambda item: (-item["count"], item.get("position", 9999), item["word"]))

        return hotlist_stats

    def cleanup(self):
        if self._storage_manager:
            self._storage_manager.cleanup_old_data()
            self._storage_manager.cleanup()
            self._storage_manager = None
