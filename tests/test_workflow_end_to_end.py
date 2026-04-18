import json
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from newspulse.context import AppContext
from newspulse.storage import get_storage_manager
from newspulse.storage.base import NewsData, NewsItem
from newspulse.workflow.delivery import DeliveryService, GenericWebhookDeliveryAdapter
from newspulse.workflow.insight.ai import AIInsightStrategy
from newspulse.workflow.insight.service import InsightService
from newspulse.workflow.localization import LocalizationService
from newspulse.workflow.localization.ai import AILocalizationStrategy
from newspulse.workflow.selection.ai import AISelectionStrategy
from newspulse.workflow.selection.service import SelectionService
from newspulse.workflow.shared.ai_runtime.prompts import PromptTemplate


def _today_at(ctx: AppContext, time_text: str) -> str:
    return f"{ctx.format_date()} {time_text}"


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip(), encoding="utf-8")


def _write_config_files(config_root: Path) -> None:
    _write_text(
        config_root / "custom" / "keyword" / "topics.txt",
        """
        [WORD_GROUPS]
        [AI]
        OpenAI
        agent
        productivity

        [Startups]
        startup
        launch
        Product Hunt
        """,
    )
    _write_text(
        config_root / "custom" / "ai" / "interests.txt",
        """
        AI agents and coding tools
        startup launches
        """,
    )
    _write_text(
        config_root / "ai_filter" / "prompt.txt",
        """
        [user]
        TAGS:
        {tags_list}
        NEWS:
        {news_list}
        INTERESTS:
        {interests_content}
        """,
    )
    _write_text(
        config_root / "ai_filter" / "extract_prompt.txt",
        """
        [user]
        INTERESTS:
        {interests_content}
        """,
    )
    _write_text(
        config_root / "ai_filter" / "update_tags_prompt.txt",
        """
        [user]
        OLD:
        {old_tags_json}
        NEW:
        {interests_content}
        """,
    )


def _build_config(
    config_root: Path,
    output_dir: Path,
    *,
    selection_strategy: str = "keyword",
    ai_analysis_enabled: bool = False,
    ai_translation_enabled: bool = False,
) -> dict:
    return {
        "TIMEZONE": "Asia/Shanghai",
        "RANK_THRESHOLD": 5,
        "WEIGHT_CONFIG": {
            "RANK_WEIGHT": 0.6,
            "FREQUENCY_WEIGHT": 0.3,
            "HOTNESS_WEIGHT": 0.1,
        },
        "PLATFORMS": [
            {"id": "hackernews", "name": "Hacker News"},
            {"id": "producthunt", "name": "Product Hunt"},
        ],
        "DISPLAY_MODE": "keyword",
        "DISPLAY": {
            "REGION_ORDER": ["hotlist", "new_items", "standalone", "insight"],
            "REGIONS": {
                "HOTLIST": True,
                "NEW_ITEMS": True,
                "STANDALONE": True,
                "AI_ANALYSIS": True,
            },
            "STANDALONE": {"PLATFORMS": ["producthunt"], "MAX_ITEMS": 10},
        },
        "FILTER": {
            "METHOD": selection_strategy,
            "FREQUENCY_FILE": "topics.txt",
            "PRIORITY_SORT_ENABLED": True,
        },
        "AI": {"MODEL": "openai/base", "API_KEY": "test-key", "TIMEOUT": 30},
        "AI_FILTER_MODEL": {"MODEL": "openai/filter", "API_KEY": "test-key", "TIMEOUT": 30},
        "AI_ANALYSIS_MODEL": {"MODEL": "openai/analysis", "API_KEY": "test-key", "TIMEOUT": 30},
        "AI_TRANSLATION_MODEL": {"MODEL": "openai/translation", "API_KEY": "test-key", "TIMEOUT": 30},
        "AI_FILTER": {
            "INTERESTS_FILE": "interests.txt",
            "BATCH_SIZE": 2,
            "BATCH_INTERVAL": 0,
            "MIN_SCORE": 0.8,
            "FALLBACK_TO_KEYWORD": True,
        },
        "AI_ANALYSIS": {
            "ENABLED": ai_analysis_enabled,
            "STRATEGY": "ai" if ai_analysis_enabled else "noop",
            "MODE": "daily",
            "MAX_NEWS_FOR_ANALYSIS": 5,
            "INCLUDE_STANDALONE": True,
            "INCLUDE_RANK_TIMELINE": True,
            "LANGUAGE": "Chinese",
            "PROMPT_FILE": "ai_analysis_prompt.txt",
        },
        "AI_TRANSLATION": {
            "ENABLED": ai_translation_enabled,
            "STRATEGY": "ai" if ai_translation_enabled else "noop",
            "LANGUAGE": "Chinese",
            "PROMPT_FILE": "ai_translation_prompt.txt",
            "SCOPE": {
                "HOTLIST": True,
                "NEW_ITEMS": True,
                "STANDALONE": True,
                "INSIGHT": True,
            },
        },
        "ENABLE_NOTIFICATION": True,
        "GENERIC_WEBHOOK_URL": "https://example.com/webhook",
        "GENERIC_WEBHOOK_TEMPLATE": "",
        "MESSAGE_BATCH_SIZE": 4000,
        "STORAGE": {
            "BACKEND": "local",
            "FORMATS": {"TXT": False, "HTML": True},
            "LOCAL": {"DATA_DIR": str(output_dir), "RETENTION_DAYS": 0},
        },
        "MAX_NEWS_PER_KEYWORD": 0,
        "SORT_BY_POSITION_FIRST": False,
        "SHOW_VERSION_UPDATE": False,
        "DEBUG": False,
        "_PATHS": {"CONFIG_ROOT": str(config_root)},
    }


class RoutingAISelectionClient:
    def chat(self, messages, **kwargs):
        user_content = messages[-1]["content"]
        if user_content.startswith("INTERESTS:"):
            return json.dumps(
                {
                    "tags": [
                        {"tag": "AI Agents", "description": "AI coding agents"},
                        {"tag": "Startups", "description": "startup launches"},
                    ]
                }
            )

        tag_ids = {}
        for line in user_content.splitlines():
            if ". " in line and ":" in line and "[" not in line:
                prefix, rest = line.split(". ", 1)
                if prefix.isdigit():
                    tag_ids[rest.split(":", 1)[0].strip()] = int(prefix)

        results = []
        for line in user_content.splitlines():
            if ". [" not in line:
                continue
            prompt_id = int(line.split(".", 1)[0])
            lowered = line.lower()
            if "openai" in lowered or "agent" in lowered:
                results.append({"id": prompt_id, "tag_id": tag_ids.get("AI Agents", 1), "score": 0.96})
            elif "startup" in lowered or "productivity" in lowered:
                results.append({"id": prompt_id, "tag_id": tag_ids.get("Startups", 2), "score": 0.91})
        return json.dumps(results)


class InsightClient:
    def chat(self, messages, **kwargs):
        return json.dumps(
            {
                "core_trends": "AI tools keep dominating the developer conversation.",
                "sentiment_controversy": "Developers are excited but still cautious.",
                "signals": "OpenAI launches and startup launches keep showing up together.",
                "outlook_strategy": "Keep tracking launch cadence and developer adoption.",
                "standalone_summaries": {"Product Hunt": "Startup launches remain a strong secondary signal."},
            }
        )


class RecordingLocalizationClient:
    def __init__(self):
        self.calls = []

    def chat(self, messages, **kwargs):
        texts = []
        for line in messages[-1]["content"].splitlines():
            stripped = line.strip()
            if not stripped.startswith("[") or "]" not in stripped:
                continue
            texts.append(stripped[stripped.index("]") + 1 :].strip())

        self.calls.append(texts)
        return "\n".join(
            f"[{index}] ZH:{text}"
            for index, text in enumerate(texts, start=1)
        )


class RecordingSender:
    def __init__(self):
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(dict(kwargs))
        return True


class NativeWorkflowEndToEndTest(unittest.TestCase):
    def _create_context(
        self,
        tmp: str,
        *,
        selection_strategy: str = "keyword",
        ai_analysis_enabled: bool = False,
        ai_translation_enabled: bool = False,
    ) -> AppContext:
        root = Path(tmp)
        config_root = root / "config"
        output_dir = root / "output"
        _write_config_files(config_root)
        ctx = AppContext(
            _build_config(
                config_root,
                output_dir,
                selection_strategy=selection_strategy,
                ai_analysis_enabled=ai_analysis_enabled,
                ai_translation_enabled=ai_translation_enabled,
            )
        )
        ctx._storage_manager = get_storage_manager(
            backend_type="local",
            data_dir=str(output_dir),
            enable_txt=False,
            enable_html=True,
            timezone=ctx.timezone,
            force_new=True,
        )
        return ctx

    def _seed_hotlist(self, ctx: AppContext) -> None:
        ctx.get_storage_manager().save_news_data(
            NewsData(
                date=ctx.format_date(),
                crawl_time=_today_at(ctx, "10:00:00"),
                items={
                    "hackernews": [
                        NewsItem(
                            title="OpenAI launches a new coding agent",
                            source_id="hackernews",
                            source_name="Hacker News",
                            rank=1,
                            url="https://example.com/openai",
                            mobile_url="https://m.example.com/openai",
                            crawl_time=_today_at(ctx, "10:00:00"),
                            ranks=[1],
                            first_time=_today_at(ctx, "10:00:00"),
                            last_time=_today_at(ctx, "10:00:00"),
                            count=1,
                            rank_timeline=[{"time": "10:00", "rank": 1}],
                        ),
                        NewsItem(
                            title="NBA finals schedule announced",
                            source_id="hackernews",
                            source_name="Hacker News",
                            rank=3,
                            url="https://example.com/nba",
                            mobile_url="https://m.example.com/nba",
                            crawl_time=_today_at(ctx, "10:00:00"),
                            ranks=[3],
                            first_time=_today_at(ctx, "10:00:00"),
                            last_time=_today_at(ctx, "10:00:00"),
                            count=1,
                            rank_timeline=[{"time": "10:00", "rank": 3}],
                        ),
                    ],
                    "producthunt": [
                        NewsItem(
                            title="Startup launches AI productivity app",
                            source_id="producthunt",
                            source_name="Product Hunt",
                            rank=2,
                            url="https://example.com/startup",
                            mobile_url="https://m.example.com/startup",
                            crawl_time=_today_at(ctx, "10:00:00"),
                            ranks=[2],
                            first_time=_today_at(ctx, "10:00:00"),
                            last_time=_today_at(ctx, "10:00:00"),
                            count=1,
                            rank_timeline=[{"time": "10:00", "rank": 2}],
                        )
                    ],
                },
                id_to_name={"hackernews": "Hacker News", "producthunt": "Product Hunt"},
                failed_ids=[],
            )
        )

    def _build_ai_selection_service(self, ctx: AppContext) -> SelectionService:
        classify_prompt = PromptTemplate(
            path=Path("selection-classify.txt"),
            user_prompt="TAGS:\n{tags_list}\nNEWS:\n{news_list}\nINTERESTS:\n{interests_content}",
        )
        extract_prompt = PromptTemplate(
            path=Path("selection-extract.txt"),
            user_prompt="INTERESTS:\n{interests_content}",
        )
        update_tags_prompt = PromptTemplate(
            path=Path("selection-update.txt"),
            user_prompt="OLD:\n{old_tags_json}\nNEW:\n{interests_content}",
        )
        ai_strategy = AISelectionStrategy(
            storage_manager=ctx.get_storage_manager(),
            client=RoutingAISelectionClient(),
            filter_config=ctx.ai_filter_config,
            config_root=ctx.config_root,
            sleep_func=lambda _: None,
            classify_prompt=classify_prompt,
            extract_prompt=extract_prompt,
            update_tags_prompt=update_tags_prompt,
        )
        return SelectionService(
            config_root=str(ctx.config_root),
            rank_threshold=ctx.rank_threshold,
            weight_config=ctx.weight_config,
            max_news_per_keyword=ctx.config.get("MAX_NEWS_PER_KEYWORD", 0),
            sort_by_position_first=ctx.config.get("SORT_BY_POSITION_FIRST", False),
            ai_strategy=ai_strategy,
        )

    def _build_ai_insight_service(self, ctx: AppContext) -> InsightService:
        prompt_template = PromptTemplate(
            path=Path("insight-prompt.txt"),
            user_prompt=(
                "MODE={report_mode}\n"
                "TYPE={report_type}\n"
                "COUNT={news_count}\n"
                "PLATFORMS={platforms}\n"
                "KEYWORDS={keywords}\n"
                "NEWS:\n{news_content}\n"
                "STANDALONE:\n{standalone_content}\n"
                "LANG={language}"
            ),
        )
        return InsightService(
            ai_strategy=AIInsightStrategy(
                client=InsightClient(),
                analysis_config=ctx.config["AI_ANALYSIS"],
                prompt_template=prompt_template,
            )
        )

    def _build_localization_service(self, client: RecordingLocalizationClient) -> LocalizationService:
        prompt_template = PromptTemplate(
            path=Path("localization-prompt.txt"),
            user_prompt="LANG={target_language}\n{content}",
        )
        return LocalizationService(
            ai_strategy=AILocalizationStrategy(
                client=client,
                prompt_template=prompt_template,
            )
        )

    def _build_delivery_service(self, ctx: AppContext, sender: RecordingSender) -> DeliveryService:
        return DeliveryService(
            generic_webhook_adapter=GenericWebhookDeliveryAdapter(ctx.config, sender_func=sender)
        )

    def _run_pipeline(
        self,
        ctx: AppContext,
        *,
        selection_strategy: str,
        selection_service: SelectionService | None = None,
        insight_service: InsightService | None = None,
        localization_service: LocalizationService | None = None,
        delivery_service: DeliveryService | None = None,
    ):
        snapshot, selection = ctx.run_selection_stage(
            mode="daily",
            strategy=selection_strategy,
            frequency_file="topics.txt",
            interests_file="interests.txt" if selection_strategy == "ai" else None,
            selection_service=selection_service,
        )
        insight = ctx.run_insight_stage(
            report_mode="daily",
            snapshot=snapshot,
            selection=selection,
            strategy=selection_strategy,
            frequency_file="topics.txt",
            interests_file="interests.txt" if selection_strategy == "ai" else None,
            insight_service=insight_service,
        )
        report = ctx.assemble_renderable_report(snapshot, selection, insight)
        localized = ctx.run_localization_stage(report, localization_service=localization_service)
        render_result = ctx.run_render_stage(localized, emit_html=True, emit_notification=True)
        delivery_result = ctx.run_delivery_stage(render_result.payloads, delivery_service=delivery_service)
        return snapshot, selection, insight, localized, render_result, delivery_result

    def test_end_to_end_runs_with_all_ai_disabled(self):
        with TemporaryDirectory() as tmp:
            ctx = self._create_context(tmp)
            sender = RecordingSender()
            try:
                self._seed_hotlist(ctx)
                _, selection, insight, localized, render_result, delivery_result = self._run_pipeline(
                    ctx,
                    selection_strategy="keyword",
                    delivery_service=self._build_delivery_service(ctx, sender),
                )

                joined_payload = "\n".join(payload.content for payload in render_result.payloads)
                self.assertEqual(selection.strategy, "keyword")
                self.assertEqual(insight.strategy, "noop")
                self.assertEqual(localized.translation_meta["strategy"], "noop")
                self.assertEqual(
                    [item.title for item in selection.selected_new_items],
                    ["OpenAI launches a new coding agent", "Startup launches AI productivity app"],
                )
                self.assertIn("OpenAI launches a new coding agent", render_result.html.content)
                self.assertIn("OpenAI launches a new coding agent", joined_payload)
                self.assertNotIn("NBA finals schedule announced", render_result.html.content)
                self.assertNotIn("NBA finals schedule announced", joined_payload)
                self.assertTrue(delivery_result.success)
                self.assertTrue(sender.calls)
            finally:
                ctx.cleanup()

    def test_end_to_end_supports_ai_selection_only(self):
        with TemporaryDirectory() as tmp:
            ctx = self._create_context(tmp, selection_strategy="ai")
            sender = RecordingSender()
            try:
                self._seed_hotlist(ctx)
                _, selection, insight, localized, render_result, _ = self._run_pipeline(
                    ctx,
                    selection_strategy="ai",
                    selection_service=self._build_ai_selection_service(ctx),
                    delivery_service=self._build_delivery_service(ctx, sender),
                )

                joined_payload = "\n".join(payload.content for payload in render_result.payloads)
                self.assertEqual(selection.strategy, "ai")
                self.assertGreaterEqual(selection.total_selected, 2)
                self.assertEqual(insight.strategy, "noop")
                self.assertEqual(localized.translation_meta["strategy"], "noop")
                self.assertIn("OpenAI launches a new coding agent", joined_payload)
                self.assertNotIn("NBA finals schedule announced", joined_payload)
                self.assertEqual(
                    [item.title for item in selection.selected_new_items],
                    ["OpenAI launches a new coding agent", "Startup launches AI productivity app"],
                )
                self.assertNotIn("AI tools keep dominating the developer conversation.", joined_payload)
            finally:
                ctx.cleanup()

    def test_end_to_end_supports_ai_selection_and_insight(self):
        with TemporaryDirectory() as tmp:
            ctx = self._create_context(tmp, selection_strategy="ai", ai_analysis_enabled=True)
            sender = RecordingSender()
            try:
                self._seed_hotlist(ctx)
                _, selection, insight, _, render_result, delivery_result = self._run_pipeline(
                    ctx,
                    selection_strategy="ai",
                    selection_service=self._build_ai_selection_service(ctx),
                    insight_service=self._build_ai_insight_service(ctx),
                    delivery_service=self._build_delivery_service(ctx, sender),
                )

                joined_payload = "\n".join(payload.content for payload in render_result.payloads)
                self.assertEqual(selection.strategy, "ai")
                self.assertTrue(insight.enabled)
                self.assertEqual(insight.diagnostics["analyzed_items"], 2)
                self.assertIn("AI tools keep dominating the developer conversation.", render_result.html.content)
                self.assertIn("AI tools keep dominating the developer conversation.", joined_payload)
                self.assertNotIn("NBA finals schedule announced", render_result.html.content)
                self.assertNotIn("NBA finals schedule announced", joined_payload)
                self.assertTrue(delivery_result.success)
                self.assertTrue(sender.calls)
            finally:
                ctx.cleanup()

    def test_end_to_end_reuses_same_translation_for_html_and_notification(self):
        with TemporaryDirectory() as tmp:
            ctx = self._create_context(tmp, ai_analysis_enabled=True, ai_translation_enabled=True)
            localization_client = RecordingLocalizationClient()
            sender = RecordingSender()
            try:
                self._seed_hotlist(ctx)
                _, _, _, localized, render_result, delivery_result = self._run_pipeline(
                    ctx,
                    selection_strategy="keyword",
                    insight_service=self._build_ai_insight_service(ctx),
                    localization_service=self._build_localization_service(localization_client),
                    delivery_service=self._build_delivery_service(ctx, sender),
                )

                translated_titles = set(localized.localized_titles.values())
                translated_title = "ZH:OpenAI launches a new coding agent"
                translated_section = localized.localized_sections["core_trends"]
                joined_payload = "\n".join(payload.content for payload in render_result.payloads)
                delivered_content = "\n".join(call["content"] for call in sender.calls)

                self.assertIn(translated_title, translated_titles)
                self.assertEqual(translated_section, "ZH:AI tools keep dominating the developer conversation.")
                self.assertEqual(
                    [item.title for item in localized.base_report.new_items],
                    [
                        "OpenAI launches a new coding agent",
                        "Startup launches AI productivity app",
                    ],
                )
                self.assertIn(translated_title, render_result.html.content)
                self.assertIn(translated_title, joined_payload)
                self.assertIn(translated_title, delivered_content)
                self.assertIn(translated_section, render_result.html.content)
                self.assertIn(translated_section, joined_payload)
                self.assertNotIn("ZH:NBA finals schedule announced", render_result.html.content)
                self.assertNotIn("ZH:NBA finals schedule announced", joined_payload)
                self.assertTrue(delivery_result.success)
                self.assertEqual(len(localization_client.calls), 2)
            finally:
                ctx.cleanup()


if __name__ == "__main__":
    unittest.main()
