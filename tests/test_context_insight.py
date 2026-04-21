import unittest
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from newspulse.context import AppContext
from newspulse.storage import get_storage_manager
from newspulse.workflow.shared.contracts import HotlistItem, HotlistSnapshot, InsightResult, InsightSection, SelectionResult


class RecordingInsightService:
    def __init__(self):
        self.calls = []

    def run(self, snapshot, selection, options):
        self.calls.append((snapshot, selection, options))
        return InsightResult(
            enabled=True,
            strategy='ai',
            sections=[InsightSection(key='core_trends', title='Core Trends', content='ok')],
            diagnostics={'report_mode': options.mode, 'analyzed_items': len(selection.selected_items)},
        )


class AppContextInsightStageTest(unittest.TestCase):
    def _build_context(self, tmp: str, *, ai_mode: str = 'follow_report') -> AppContext:
        root = str(tmp)
        config = {
            'TIMEZONE': 'Asia/Shanghai',
            'RANK_THRESHOLD': 10,
            'WEIGHT_CONFIG': {},
            'PLATFORMS': [{'id': 'hackernews', 'name': 'Hacker News'}],
            'DISPLAY_MODE': 'keyword',
            'DISPLAY': {
                'REGION_ORDER': ['hotlist', 'new_items', 'standalone', 'insight'],
                'REGIONS': {'NEW_ITEMS': True},
                'STANDALONE': {'PLATFORMS': [], 'MAX_ITEMS': 10},
            },
            'FILTER': {'METHOD': 'keyword', 'PRIORITY_SORT_ENABLED': False},
            'AI': {'MODEL': 'openai/base', 'API_KEY': 'test-key', 'TIMEOUT': 30},
            'AI_ANALYSIS_MODEL': {'MODEL': 'openai/analysis', 'API_KEY': 'test-key', 'TIMEOUT': 30},
            'AI_ANALYSIS': {
                'ENABLED': True,
                'STRATEGY': 'ai',
                'MODE': ai_mode,
                'MAX_ITEMS': 7,
                'LANGUAGE': 'Chinese',
                'PROMPT_FILE': 'ai_analysis_prompt.txt',
                'ITEM_PROMPT_FILE': 'ai_insight_item_prompt.txt',
                'CONTENT': {'CACHE_ENABLED': True, 'TIMEOUT': 12, 'REDUCED_CHARS': 1500},
                'ITEM_ANALYSIS': {'PROMPT_FILE': 'ai_insight_item_prompt.txt', 'MIN_EVIDENCE_SENTENCES': 2},
                'AGGREGATE': {'PROMPT_FILE': 'ai_analysis_prompt.txt'},
            },
            'STORAGE': {
                'BACKEND': 'local',
                'FORMATS': {'TXT': False, 'HTML': False},
                'LOCAL': {'DATA_DIR': root, 'RETENTION_DAYS': 0},
            },
            'MAX_NEWS_PER_KEYWORD': 0,
            'SORT_BY_POSITION_FIRST': False,
            'DEBUG': False,
            '_PATHS': {'CONFIG_ROOT': 'config'},
        }
        ctx = AppContext(config)
        ctx._storage_manager = get_storage_manager(
            backend_type='local',
            data_dir=root,
            enable_txt=False,
            enable_html=False,
            timezone=ctx.timezone,
            force_new=True,
        )
        return ctx

    def _snapshot_and_selection(self):
        item = HotlistItem(
            news_item_id='1',
            source_id='hackernews',
            source_name='Hacker News',
            title='OpenAI launches a new coding agent',
            current_rank=1,
        )
        snapshot = HotlistSnapshot(mode='current', generated_at='2026-04-20 10:00:00', items=[item])
        selection = SelectionResult(strategy='keyword', selected_items=[item], total_candidates=1, total_selected=1)
        return snapshot, selection

    def test_build_insight_options_resolves_mode_in_context_layer(self):
        with TemporaryDirectory() as tmp:
            ctx = self._build_context(tmp, ai_mode='daily')
            try:
                options = ctx.build_insight_options(report_mode='current')

                self.assertTrue(options.enabled)
                self.assertEqual(options.strategy, 'ai')
                self.assertEqual(options.mode, 'current')
                self.assertEqual(options.max_items, 7)
                self.assertTrue(options.metadata['mode_resolved_by_context'])
            finally:
                ctx.cleanup()

    def test_run_insight_stage_uses_provided_snapshot_and_selection_without_hidden_reselection(self):
        with TemporaryDirectory() as tmp:
            ctx = self._build_context(tmp, ai_mode='daily')
            snapshot, selection = self._snapshot_and_selection()
            recorder = RecordingInsightService()
            ctx.run_selection_stage = lambda **kwargs: (_ for _ in ()).throw(AssertionError('run_selection_stage should not be called'))
            try:
                insight = ctx.run_insight_stage(
                    report_mode='current',
                    snapshot=snapshot,
                    selection=selection,
                    insight_service=recorder,
                )

                self.assertTrue(insight.enabled)
                self.assertEqual(insight.diagnostics['report_mode'], 'current')
                self.assertEqual(len(recorder.calls), 1)
                self.assertIs(recorder.calls[0][0], snapshot)
                self.assertIs(recorder.calls[0][1], selection)
            finally:
                ctx.cleanup()

    def test_run_insight_stage_respects_schedule_switches_and_once_recording(self):
        with TemporaryDirectory() as tmp:
            ctx = self._build_context(tmp)
            snapshot, selection = self._snapshot_and_selection()
            recorder = RecordingInsightService()
            try:
                disabled = ctx.run_insight_stage(
                    report_mode='current',
                    snapshot=snapshot,
                    selection=selection,
                    schedule=SimpleNamespace(analyze=False, once_analyze=False, period_key=None, period_name=None),
                )
                self.assertFalse(disabled.enabled)
                self.assertTrue(disabled.diagnostics['skipped'])

                schedule = SimpleNamespace(analyze=True, once_analyze=True, period_key='morning', period_name='Morning')
                result = ctx.run_insight_stage(
                    report_mode='current',
                    snapshot=snapshot,
                    selection=selection,
                    schedule=schedule,
                    insight_service=recorder,
                )

                self.assertTrue(result.enabled)
                self.assertTrue(ctx.get_storage_manager().has_period_executed(ctx.format_date(), 'morning', 'analyze'))
            finally:
                ctx.cleanup()


if __name__ == '__main__':
    unittest.main()
