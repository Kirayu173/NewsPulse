# coding=utf-8
"""Main NewsPulse pipeline implementation."""

from __future__ import annotations

import os
import webbrowser
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from newspulse import __version__
from newspulse.ai import AIAnalysisResult, AIAnalyzer
from newspulse.context import AppContext
from newspulse.core import load_config
from newspulse.core.analyzer import convert_keyword_stats_to_platform_stats
from newspulse.core.scheduler import ResolvedSchedule
from newspulse.crawler import DataFetcher
from newspulse.storage import convert_crawl_results_to_news_data
from newspulse.utils.time import DEFAULT_TIMEZONE


class NewsAnalyzer:
    """Coordinate crawling, analysis, rendering and notification."""

    MODE_STRATEGIES = {
        "incremental": {
            "mode_name": "增量",
            "description": "仅分析本次抓取新增的热榜变化",
            "report_type": "增量报告",
            "should_send_notification": True,
        },
        "current": {
            "mode_name": "实时",
            "description": "基于今日已抓取数据生成当前快照",
            "report_type": "实时报告",
            "should_send_notification": True,
        },
        "daily": {
            "mode_name": "日报",
            "description": "汇总今日全部抓取数据生成日报",
            "report_type": "每日报告",
            "should_send_notification": True,
        },
    }

    def __init__(self, config: Optional[Dict] = None):
        if config is None:
            print("正在加载配置...")
            config = load_config()

        print(f"NewsPulse v{__version__} 启动中")
        print(f"已启用平台: {len(config['PLATFORMS'])}")
        print(f"时区: {config.get('TIMEZONE', DEFAULT_TIMEZONE)}")

        self.ctx = AppContext(config)
        self.request_interval = self.ctx.config["REQUEST_INTERVAL"]
        self.report_mode = self.ctx.config["REPORT_MODE"]
        self.frequency_file: Optional[str] = None
        self.filter_method: Optional[str] = None
        self.interests_file: Optional[str] = None
        self.rank_threshold = self.ctx.rank_threshold
        self.is_github_actions = os.environ.get("GITHUB_ACTIONS") == "true"
        self.is_docker_container = self._detect_docker_environment()
        self.update_info = None
        self.proxy_url = None

        self._setup_proxy()
        self.data_fetcher = DataFetcher(self.proxy_url)
        self._init_storage_manager()

    def _init_storage_manager(self) -> None:
        env_retention = os.environ.get("STORAGE_RETENTION_DAYS", "").strip()
        if env_retention:
            self.ctx.config.setdefault("STORAGE", {}).setdefault("LOCAL", {})["RETENTION_DAYS"] = int(env_retention)

        self.storage_manager = self.ctx.get_storage_manager()
        print(f"存储: {self.storage_manager.backend_name}")

        retention_days = self.ctx.config.get("STORAGE", {}).get("LOCAL", {}).get("RETENTION_DAYS", 0)
        if retention_days > 0:
            print(f"数据保留: {retention_days} 天")

    def _detect_docker_environment(self) -> bool:
        try:
            if os.environ.get("DOCKER_CONTAINER") == "true":
                return True
            return os.path.exists("/.dockerenv")
        except Exception:
            return False

    def _should_open_browser(self) -> bool:
        return not self.is_github_actions and not self.is_docker_container

    def _setup_proxy(self) -> None:
        if not self.is_github_actions and self.ctx.config["USE_PROXY"]:
            self.proxy_url = self.ctx.config["DEFAULT_PROXY"]
            print("已启用代理")
        elif not self.is_github_actions:
            print("未启用代理")
        else:
            print("GitHub Actions 环境，跳过代理设置")

    def _set_update_info_from_config(self) -> None:
        try:
            version_url = self.ctx.config.get("VERSION_CHECK_URL", "")
            if not version_url:
                return
            from newspulse.cli.versioning import _fetch_remote_version, _parse_version

            remote_version = _fetch_remote_version(version_url, self.proxy_url)
            if remote_version and _parse_version(__version__) < _parse_version(remote_version):
                self.update_info = {
                    "current_version": __version__,
                    "remote_version": remote_version,
                }
        except Exception as exc:
            print(f"版本检查失败: {exc}")

    def _get_mode_strategy(self) -> Dict:
        return self.MODE_STRATEGIES.get(self.report_mode, self.MODE_STRATEGIES["daily"])

    def _has_notification_configured(self) -> bool:
        return bool(self.ctx.config.get("GENERIC_WEBHOOK_URL"))

    def _has_valid_content(self, stats: List[Dict], new_titles: Optional[Dict] = None) -> bool:
        if self.report_mode == "incremental":
            return any(stat.get("count", 0) > 0 for stat in stats)
        if self.report_mode == "current":
            return any(stat.get("count", 0) > 0 for stat in stats)
        has_matched_news = any(stat.get("count", 0) > 0 for stat in stats)
        has_new_news = bool(new_titles and any(len(titles) > 0 for titles in new_titles.values()))
        return has_matched_news or has_new_news

    def _prepare_ai_analysis_data(
        self,
        ai_mode: str,
        current_results: Optional[Dict] = None,
        current_id_to_name: Optional[Dict] = None,
    ) -> Tuple[List[Dict], Optional[Dict]]:
        try:
            word_groups, filter_words, global_filters = self.ctx.load_frequency_words(self.frequency_file)

            if ai_mode == "incremental":
                if not current_results or not current_id_to_name:
                    print("[AI] incremental 模式缺少当前抓取数据")
                    return [], None

                time_info = self.ctx.format_time()
                title_info = self._prepare_current_title_info(current_results, time_info)
                new_titles = self.ctx.detect_new_titles(list(current_results.keys()))
                stats, _ = self.ctx.count_frequency(
                    current_results,
                    word_groups,
                    filter_words,
                    current_id_to_name,
                    title_info,
                    new_titles,
                    mode="incremental",
                    global_filters=global_filters,
                    quiet=True,
                )
                if self.ctx.display_mode == "platform" and stats:
                    stats = convert_keyword_stats_to_platform_stats(
                        stats,
                        self.ctx.weight_config,
                        self.ctx.rank_threshold,
                    )
                return stats, current_id_to_name

            if ai_mode in ("daily", "current"):
                analysis_data = self._load_analysis_data(quiet=True)
                if not analysis_data:
                    print(f"[AI] 无法加载 {ai_mode} 模式所需的历史数据")
                    return [], None

                all_results, id_to_name, title_info, new_titles, word_groups2, filter_words2, global_filters2 = analysis_data
                stats, _ = self.ctx.count_frequency(
                    all_results,
                    word_groups2,
                    filter_words2,
                    id_to_name,
                    title_info,
                    new_titles,
                    mode=ai_mode,
                    global_filters=global_filters2,
                    quiet=True,
                )
                if self.ctx.display_mode == "platform" and stats:
                    stats = convert_keyword_stats_to_platform_stats(
                        stats,
                        self.ctx.weight_config,
                        self.ctx.rank_threshold,
                    )
                return stats, id_to_name

            print(f"[AI] 不支持的 AI 模式: {ai_mode}")
            return [], None
        except Exception as exc:
            print(f"[AI] 准备 {ai_mode} 分析数据失败: {exc}")
            if self.ctx.config.get("DEBUG", False):
                raise
            return [], None

    def _run_ai_analysis(
        self,
        stats: List[Dict],
        mode: str,
        report_type: str,
        id_to_name: Optional[Dict],
        current_results: Optional[Dict] = None,
        schedule: Optional[ResolvedSchedule] = None,
        standalone_data: Optional[Dict] = None,
    ) -> Optional[AIAnalysisResult]:
        analysis_config = self.ctx.config.get("AI_ANALYSIS", {})
        if not analysis_config.get("ENABLED", False):
            return None

        schedule = schedule or self.ctx.create_scheduler().resolve()
        if not schedule.analyze:
            print("[AI] 当前时段未配置 AI 分析")
            return None

        if schedule.once_analyze and schedule.period_key:
            scheduler = self.ctx.create_scheduler()
            date_str = self.ctx.format_date()
            if scheduler.already_executed(schedule.period_key, "analyze", date_str):
                print(f"[AI] 分析计划 {schedule.period_name or schedule.period_key} 今日已执行")
                return None
            print(f"[AI] 分析计划 {schedule.period_name or schedule.period_key} 准备执行")

        print("[AI] 开始执行 AI 分析...")
        ai_config = self.ctx.ai_analysis_model_config
        analyzer = AIAnalyzer(ai_config, analysis_config, self.ctx.get_time, debug=self.ctx.config.get("DEBUG", False))

        ai_mode_config = analysis_config.get("MODE", "follow_report")
        ai_mode = mode
        ai_stats = stats
        ai_id_to_name = id_to_name

        if ai_mode_config in ("daily", "current", "incremental") and ai_mode_config != mode:
            print(f"[AI] AI 模式切换为: {ai_mode_config} (报告模式: {mode})")
            ai_stats, ai_id_to_name = self._prepare_ai_analysis_data(ai_mode_config, current_results, id_to_name)
            if ai_stats:
                ai_mode = ai_mode_config
            else:
                print(f"[AI] 无法准备 {ai_mode_config} 模式的数据，回退到当前报告数据")
                ai_stats = stats
                ai_id_to_name = id_to_name
        elif ai_mode_config not in ("follow_report", "daily", "current", "incremental"):
            print(f"[AI] 未识别 ai_analysis.mode={ai_mode_config}，按 follow_report 处理")

        platforms = list(ai_id_to_name.values()) if ai_id_to_name else []
        keywords = [stat.get("word", "") for stat in ai_stats if stat.get("word")]
        report_type_by_mode = {
            "daily": "每日报告",
            "current": "实时报告",
            "incremental": "增量报告",
        }
        ai_report_type = report_type_by_mode.get(ai_mode, report_type)

        result = analyzer.analyze(
            stats=ai_stats,
            report_mode=ai_mode,
            report_type=ai_report_type,
            platforms=platforms,
            keywords=keywords,
            standalone_data=standalone_data,
        )

        if result.success:
            result.ai_mode = ai_mode
            if result.error:
                print(f"[AI] 分析完成，但有警告: {result.error}")
            else:
                print("[AI] 分析完成")
            if schedule.once_analyze and schedule.period_key:
                scheduler = self.ctx.create_scheduler()
                scheduler.record_execution(schedule.period_key, "analyze", self.ctx.format_date())
        elif result.skipped:
            print(f"[AI] {result.error}")
        else:
            print(f"[AI] 分析失败: {result.error}")

        return result

    def _load_analysis_data(
        self,
        quiet: bool = False,
    ) -> Optional[Tuple[Dict, Dict, Dict, Dict, List, List, List]]:
        try:
            current_platform_ids = self.ctx.platform_ids
            if not quiet:
                print(f"当前平台: {current_platform_ids}")

            all_results, id_to_name, title_info = self.ctx.read_today_titles(current_platform_ids, quiet=quiet)
            if not all_results:
                if not quiet:
                    print("未读取到今日历史数据")
                return None

            total_titles = sum(len(titles) for titles in all_results.values())
            if not quiet:
                print(f"共加载 {total_titles} 条历史标题用于分析")

            new_titles = self.ctx.detect_new_titles(current_platform_ids, quiet=quiet)
            word_groups, filter_words, global_filters = self.ctx.load_frequency_words(self.frequency_file)
            return (
                all_results,
                id_to_name,
                title_info,
                new_titles,
                word_groups,
                filter_words,
                global_filters,
            )
        except Exception as exc:
            print(f"读取分析数据失败: {exc}")
            return None

    def _prepare_current_title_info(self, results: Dict, time_info: str) -> Dict:
        title_info: Dict[str, Dict] = {}
        for source_id, titles_data in results.items():
            title_info[source_id] = {}
            for title, title_data in titles_data.items():
                title_info[source_id][title] = {
                    "first_time": time_info,
                    "last_time": time_info,
                    "count": 1,
                    "ranks": title_data.get("ranks", []),
                    "url": title_data.get("url", ""),
                    "mobileUrl": title_data.get("mobileUrl", ""),
                }
        return title_info

    def _prepare_standalone_data(
        self,
        results: Dict,
        id_to_name: Dict,
        title_info: Optional[Dict] = None,
    ) -> Optional[Dict]:
        display_config = self.ctx.config.get("DISPLAY", {})
        standalone_config = display_config.get("STANDALONE", {})
        platform_ids = standalone_config.get("PLATFORMS", [])
        max_items = standalone_config.get("MAX_ITEMS", 20)
        if not platform_ids:
            return None

        latest_time = None
        if title_info:
            for source_titles in title_info.values():
                for title_data in source_titles.values():
                    last_time = title_data.get("last_time", "")
                    if last_time and (latest_time is None or last_time > latest_time):
                        latest_time = last_time

        standalone_platforms: List[Dict] = []
        for platform_id in platform_ids:
            if platform_id not in results:
                continue

            items: List[Dict] = []
            for title, title_data in results[platform_id].items():
                meta = title_info.get(platform_id, {}).get(title, {}) if title_info else {}
                if latest_time and meta and meta.get("last_time") != latest_time:
                    continue

                current_ranks = title_data.get("ranks", [])
                current_rank = current_ranks[-1] if current_ranks else 0
                historical_ranks = list(meta.get("ranks", []))
                display_ranks = historical_ranks[:]
                for rank in current_ranks:
                    if rank not in display_ranks:
                        display_ranks.append(rank)

                items.append(
                    {
                        "title": title,
                        "url": title_data.get("url", ""),
                        "mobileUrl": title_data.get("mobileUrl", ""),
                        "rank": current_rank,
                        "ranks": display_ranks or current_ranks,
                        "first_time": meta.get("first_time", ""),
                        "last_time": meta.get("last_time", ""),
                        "count": meta.get("count", 1),
                        "rank_timeline": meta.get("rank_timeline", []),
                    }
                )

            items.sort(key=lambda item: item["rank"] if item["rank"] > 0 else 9999)
            if max_items > 0:
                items = items[:max_items]

            if items:
                standalone_platforms.append(
                    {
                        "id": platform_id,
                        "name": id_to_name.get(platform_id, platform_id),
                        "items": items,
                    }
                )

        if not standalone_platforms:
            return None
        return {"platforms": standalone_platforms}

    def _run_analysis_pipeline(
        self,
        data_source: Dict,
        mode: str,
        title_info: Dict,
        new_titles: Dict,
        word_groups: List[Dict],
        filter_words: List[str],
        id_to_name: Dict,
        failed_ids: Optional[List] = None,
        global_filters: Optional[List[str]] = None,
        quiet: bool = False,
        standalone_data: Optional[Dict] = None,
        schedule: Optional[ResolvedSchedule] = None,
    ) -> Tuple[List[Dict], Optional[str], Optional[AIAnalysisResult]]:
        total_titles = sum(len(titles) for titles in data_source.values())

        if self.filter_method == "ai":
            print("[筛选] 使用 AI 筛选模式")
            ai_filter_result = self.ctx.run_ai_filter(interests_file=self.interests_file)
            if ai_filter_result and ai_filter_result.success:
                print(
                    f"[筛选] AI 筛选结果: {ai_filter_result.total_matched} 条新闻, "
                    f"{len(ai_filter_result.tags)} 个标签"
                )
                stats = self.ctx.convert_ai_filter_to_report_data(
                    ai_filter_result,
                    mode=mode,
                    new_titles=new_titles,
                )
            else:
                error_msg = ai_filter_result.error if ai_filter_result else "未知错误"
                print(f"[筛选] AI 筛选失败: {error_msg}，回退到频率统计")
                stats, total_titles = self.ctx.count_frequency(
                    data_source,
                    word_groups,
                    filter_words,
                    id_to_name,
                    title_info,
                    new_titles,
                    mode=mode,
                    global_filters=global_filters,
                    quiet=quiet,
                )
        else:
            stats, total_titles = self.ctx.count_frequency(
                data_source,
                word_groups,
                filter_words,
                id_to_name,
                title_info,
                new_titles,
                mode=mode,
                global_filters=global_filters,
                quiet=quiet,
            )

        if self.ctx.display_mode == "platform" and stats:
            stats = convert_keyword_stats_to_platform_stats(
                stats,
                self.ctx.weight_config,
                self.ctx.rank_threshold,
            )

        ai_result = None
        if self.ctx.config.get("AI_ANALYSIS", {}).get("ENABLED", False) and stats:
            ai_result = self._run_ai_analysis(
                stats,
                mode,
                self._get_mode_strategy()["report_type"],
                id_to_name,
                current_results=data_source,
                schedule=schedule,
                standalone_data=standalone_data,
            )

        html_file = None
        if self.ctx.config["STORAGE"]["FORMATS"].get("HTML", True):
            html_file = self.ctx.generate_html(
                stats,
                total_titles,
                failed_ids=failed_ids,
                new_titles=new_titles,
                id_to_name=id_to_name,
                mode=mode,
                update_info=self.update_info if self.ctx.config.get("SHOW_VERSION_UPDATE", False) else None,
                ai_analysis=ai_result,
                standalone_data=standalone_data,
                frequency_file=self.frequency_file,
            )

        return stats, html_file, ai_result

    def _send_notification_if_needed(
        self,
        stats: List[Dict],
        report_type: str,
        mode: str,
        failed_ids: Optional[List] = None,
        new_titles: Optional[Dict] = None,
        id_to_name: Optional[Dict] = None,
        html_file_path: Optional[str] = None,
        standalone_data: Optional[Dict] = None,
        ai_result: Optional[AIAnalysisResult] = None,
        current_results: Optional[Dict] = None,
        schedule: Optional[ResolvedSchedule] = None,
    ) -> bool:
        has_notification = self._has_notification_configured()
        cfg = self.ctx.config
        has_news_content = self._has_valid_content(stats, new_titles)

        if cfg["ENABLE_NOTIFICATION"] and has_notification and has_news_content:
            schedule = schedule or self.ctx.create_scheduler().resolve()
            if not schedule.push:
                print("[推送] 当前时段未配置消息推送")
                return False

            if schedule.once_push and schedule.period_key:
                scheduler = self.ctx.create_scheduler()
                date_str = self.ctx.format_date()
                if scheduler.already_executed(schedule.period_key, "push", date_str):
                    print(f"[推送] 推送计划 {schedule.period_name or schedule.period_key} 今日已执行")
                    return False
                print(f"[推送] 推送计划 {schedule.period_name or schedule.period_key} 准备执行")

            if ai_result is None and cfg.get("AI_ANALYSIS", {}).get("ENABLED", False) and stats:
                ai_result = self._run_ai_analysis(
                    stats,
                    mode,
                    report_type,
                    id_to_name,
                    current_results=current_results,
                    schedule=schedule,
                    standalone_data=standalone_data,
                )

            report_data = self.ctx.prepare_report(
                stats,
                failed_ids,
                new_titles,
                id_to_name,
                mode,
                frequency_file=self.frequency_file,
            )
            dispatcher = self.ctx.create_notification_dispatcher()
            results = dispatcher.dispatch_all(
                report_data=report_data,
                report_type=report_type,
                update_info=self.update_info if cfg.get("SHOW_VERSION_UPDATE", False) else None,
                proxy_url=self.proxy_url,
                mode=mode,
                html_file_path=html_file_path,
                ai_analysis=ai_result,
                standalone_data=standalone_data,
            )

            if not results:
                print("通知渠道没有返回任何结果")
                return False

            if any(results.values()) and schedule.once_push and schedule.period_key:
                scheduler = self.ctx.create_scheduler()
                scheduler.record_execution(schedule.period_key, "push", self.ctx.format_date())

            return any(results.values())

        if cfg["ENABLE_NOTIFICATION"] and not has_notification:
            print("已启用通知，但未配置任何可用通知渠道")
        elif not cfg["ENABLE_NOTIFICATION"]:
            print(f"已关闭 {report_type} 通知发送")
        elif cfg["ENABLE_NOTIFICATION"] and has_notification and not has_news_content:
            if self.report_mode == "incremental":
                print("增量模式下没有新增内容，跳过通知")
            else:
                print(f"当前{self._get_mode_strategy()['mode_name']}没有可发送内容")
        return False

    def _initialize_and_check_config(self) -> None:
        now = self.ctx.get_time()
        print(f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")

        if not self.ctx.config["ENABLE_CRAWLER"]:
            print("爬虫已禁用（ENABLE_CRAWLER=False），程序结束")
            return

        if not self.ctx.config["ENABLE_NOTIFICATION"]:
            print("通知已禁用（ENABLE_NOTIFICATION=False），仅生成本地结果")
        elif not self._has_notification_configured():
            print("通知功能已开启，但未检测到可用渠道")
        else:
            print("通知渠道检查通过")

        mode_strategy = self._get_mode_strategy()
        print(f"模式: {self.report_mode}")
        print(f"说明: {mode_strategy['description']}")

    def _crawl_data(self) -> Tuple[Dict, Dict, List]:
        ids = []
        for platform in self.ctx.platforms:
            if "name" in platform:
                ids.append((platform["id"], platform["name"]))
            else:
                ids.append(platform["id"])

        print(f"本次抓取平台: {[p.get('name', p['id']) for p in self.ctx.platforms]}")
        print(f"请求间隔: 每个平台等待 {self.request_interval} 秒")
        self.ctx.get_data_dir().mkdir(parents=True, exist_ok=True)

        results, id_to_name, failed_ids = self.data_fetcher.crawl_websites(ids, self.request_interval)

        crawl_time = self.ctx.format_time()
        crawl_date = self.ctx.format_date()
        news_data = convert_crawl_results_to_news_data(results, id_to_name, failed_ids, crawl_time, crawl_date)

        if self.storage_manager.save_news_data(news_data):
            print(f"抓取结果已写入存储: {self.storage_manager.backend_name}")

        txt_file = self.storage_manager.save_txt_snapshot(news_data)
        if txt_file:
            print(f"TXT 快照已保存: {txt_file}")

        return results, id_to_name, failed_ids

    def _execute_mode_strategy(
        self,
        mode_strategy: Dict,
        results: Dict,
        id_to_name: Dict,
        failed_ids: List,
        schedule: Optional[ResolvedSchedule] = None,
    ) -> Optional[str]:
        schedule = schedule or self.ctx.create_scheduler().resolve()

        effective_mode = schedule.report_mode
        if effective_mode != self.report_mode:
            print(f"[计划] 模式调整: {self.report_mode} -> {effective_mode}")
        self.report_mode = effective_mode
        mode_strategy = self._get_mode_strategy()

        self.frequency_file = schedule.frequency_file
        self.filter_method = schedule.filter_method or self.ctx.filter_method
        self.interests_file = schedule.interests_file

        time_info = self.ctx.format_time()
        current_platform_ids = self.ctx.platform_ids
        new_titles = self.ctx.detect_new_titles(current_platform_ids)
        title_info = self._prepare_current_title_info(results, time_info)
        results_for_analysis = results
        id_to_name_for_analysis = id_to_name

        analysis_data = None
        if self.report_mode in ("daily", "current"):
            analysis_data = self._load_analysis_data()
            if analysis_data:
                (
                    all_results,
                    historical_id_to_name,
                    historical_title_info,
                    historical_new_titles,
                    _,
                    _,
                    _,
                ) = analysis_data
                results_for_analysis = all_results
                id_to_name_for_analysis = {**historical_id_to_name, **id_to_name}
                title_info = historical_title_info
                new_titles = historical_new_titles

        word_groups, filter_words, global_filters = self.ctx.load_frequency_words(self.frequency_file)
        standalone_data = self._prepare_standalone_data(results_for_analysis, id_to_name_for_analysis, title_info)
        stats, html_file, ai_result = self._run_analysis_pipeline(
            results_for_analysis,
            self.report_mode,
            title_info,
            new_titles,
            word_groups,
            filter_words,
            id_to_name_for_analysis,
            failed_ids=failed_ids,
            global_filters=global_filters,
            standalone_data=standalone_data,
            schedule=schedule,
        )

        if html_file:
            print(f"HTML 报告已生成: {html_file}")
            latest_file = self.ctx.get_data_dir() / "html" / "latest" / f"{self.report_mode}.html"
            print(f"最新快照链接: {latest_file}")

        if mode_strategy["should_send_notification"]:
            self._send_notification_if_needed(
                stats,
                mode_strategy["report_type"],
                self.report_mode,
                failed_ids=failed_ids,
                new_titles=new_titles,
                id_to_name=id_to_name_for_analysis,
                html_file_path=html_file,
                standalone_data=standalone_data,
                ai_result=ai_result,
                current_results=results_for_analysis,
                schedule=schedule,
            )

        if self._should_open_browser() and html_file:
            file_url = "file://" + str(Path(html_file).resolve())
            print(f"正在打开 HTML 报告: {file_url}")
            webbrowser.open(file_url)
        elif self.is_docker_container and html_file:
            print(f"HTML 报告已生成，请在容器内手动查看: {html_file}")

        return html_file

    def run(self) -> None:
        try:
            self._initialize_and_check_config()
            if not self.ctx.config["ENABLE_CRAWLER"]:
                return

            schedule = self.ctx.create_scheduler().resolve()
            if not schedule.collect:
                print("[计划] 当前时段不执行抓取任务")
                return

            mode_strategy = self._get_mode_strategy()
            results, id_to_name, failed_ids = self._crawl_data()
            self._execute_mode_strategy(mode_strategy, results, id_to_name, failed_ids, schedule=schedule)
        except Exception as exc:
            print(f"运行异常: {exc}")
            if self.ctx.config.get("DEBUG", False):
                raise
        finally:
            self.ctx.cleanup()
