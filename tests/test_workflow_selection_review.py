import json
import shutil
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from newspulse.workflow.selection.review import export_selection_outbox
from newspulse.workflow.shared.contracts import HotlistItem, HotlistSnapshot, SelectionRejectedItem, SelectionResult


class SelectionReviewExportTest(unittest.TestCase):
    def _create_workspace_tmpdir(self) -> Path:
        root = Path('.tmp-test') / 'workflow-selection-review'
        root.mkdir(parents=True, exist_ok=True)
        path = root / str(uuid.uuid4())
        path.mkdir(parents=True, exist_ok=False)
        return path

    def _build_snapshot(self) -> tuple[HotlistSnapshot, HotlistItem, HotlistItem, HotlistItem]:
        ai_item = HotlistItem(
            news_item_id='1',
            source_id='hackernews',
            source_name='Hacker News',
            title='OpenAI 发布新一代编码代理',
            summary='Agent runtime now supports tool calling and tracing.',
            current_rank=1,
            ranks=[1],
            is_new=True,
        )
        oss_item = HotlistItem(
            news_item_id='2',
            source_id='github-trending-today',
            source_name='GitHub Trending',
            title='openai/openai-agents-python',
            summary='Official OpenAI Agents SDK for Python',
            current_rank=2,
            ranks=[2],
            metadata={
                'source_context_version': 1,
                'source_kind': 'github_repository',
                'github': {
                    'language': 'Python',
                    'topics': ['openai', 'agent', 'sdk'],
                    'stars_today': 842,
                    'stars_total': 12345,
                },
            },
        )
        sports_item = HotlistItem(
            news_item_id='3',
            source_id='tencent-hot',
            source_name='腾讯热榜',
            title='Sports finals preview',
            current_rank=3,
            ranks=[3],
        )
        snapshot = HotlistSnapshot(
            mode='current',
            generated_at='2026-04-19 10:30:00',
            items=[ai_item, oss_item, sports_item],
            new_items=[ai_item],
            summary={'mode': 'current', 'total_items': 3},
        )
        return snapshot, ai_item, oss_item, sports_item

    def test_export_selection_outbox_writes_native_funnel_artifacts(self):
        snapshot, ai_item, oss_item, sports_item = self._build_snapshot()
        keyword_selection = SelectionResult(
            strategy='keyword',
            qualified_items=[ai_item, oss_item],
            rejected_items=[
                SelectionRejectedItem(
                    news_item_id=sports_item.news_item_id,
                    source_id=sports_item.source_id,
                    source_name=sports_item.source_name,
                    title=sports_item.title,
                    rejected_stage='rule',
                    rejected_reason='matched global blacklist: sports',
                )
            ],
            selected_new_items=[ai_item],
            total_candidates=3,
            total_selected=2,
            diagnostics={'blacklist_rejected_count': 1},
        )
        ai_selection = SelectionResult(
            strategy='ai',
            qualified_items=[ai_item],
            rejected_items=[
                SelectionRejectedItem(
                    news_item_id=sports_item.news_item_id,
                    source_id=sports_item.source_id,
                    source_name=sports_item.source_name,
                    title=sports_item.title,
                    rejected_stage='semantic',
                    rejected_reason='semantic score below threshold 0.55',
                ),
                SelectionRejectedItem(
                    news_item_id=oss_item.news_item_id,
                    source_id=oss_item.source_id,
                    source_name=oss_item.source_name,
                    title=oss_item.title,
                    rejected_stage='llm',
                    rejected_reason='quality score below threshold 0.70',
                    score=0.52,
                ),
            ],
            selected_new_items=[ai_item],
            total_candidates=3,
            total_selected=1,
            diagnostics={
                'semantic_enabled': True,
                'semantic_skipped': False,
                'semantic_model': 'openai/embedding-test',
                'semantic_topic_count': 2,
                'semantic_candidate_count': 2,
                'semantic_passed_count': 2,
                'semantic_rejected_count': 1,
                'semantic_topics': [
                    {
                        'topic_id': 1,
                        'label': 'AI Agents',
                        'description': 'Agent frameworks and MCP ecosystem',
                    },
                    {
                        'topic_id': 2,
                        'label': 'Open Source',
                        'description': 'Open source developer tools',
                    },
                ],
                'semantic_candidates': [
                    {
                        'news_item_id': '1',
                        'source_id': 'hackernews',
                        'title': ai_item.title,
                        'summary': ai_item.summary,
                        'topic_id': 1,
                        'topic_label': 'AI Agents',
                        'score': 0.97,
                    },
                    {
                        'news_item_id': '2',
                        'source_id': 'github-trending-today',
                        'title': oss_item.title,
                        'summary': oss_item.summary,
                        'topic_id': 2,
                        'topic_label': 'Open Source',
                        'score': 0.73,
                    },
                ],
                'llm_batch_count': 1,
                'llm_evaluated_count': 2,
                'llm_decision_count': 2,
                'min_score': 0.7,
                'focus_labels': ['AI Agents', 'Open Source'],
                'llm_decisions': [
                    {
                        'news_item_id': '1',
                        'keep': True,
                        'quality_score': 0.95,
                        'reasons': ['有信息增量'],
                        'evidence': '产品发布具备后续分析价值',
                    },
                    {
                        'news_item_id': '2',
                        'keep': True,
                        'quality_score': 0.52,
                        'reasons': ['信息密度不足'],
                        'evidence': '更新较轻',
                        'metadata': {'summary': oss_item.summary},
                    },
                ],
                'selected_matches': [
                    {
                        'news_item_id': '1',
                        'source_id': 'hackernews',
                        'title': ai_item.title,
                        'quality_score': 0.95,
                        'decision_layer': 'llm_quality_gate',
                    }
                ],
            },
        )

        tmpdir = self._create_workspace_tmpdir()
        try:
            summary = export_selection_outbox(
                outbox_dir=tmpdir,
                generated_at=datetime(2026, 4, 19, 10, 31, tzinfo=timezone.utc),
                config_path='config/config.yaml',
                storage_data_dir=Path(tmpdir) / 'stage4_storage',
                snapshot=snapshot,
                keyword_selection=keyword_selection,
                ai_selection=ai_selection,
                ai_skip_reason='',
                run_log='stage4 ok',
            )

            review_text = (tmpdir / 'stage4_selection_review.md').read_text(encoding='utf-8-sig')
            semantic_payload = json.loads((tmpdir / 'stage4_selection_semantic.json').read_text(encoding='utf-8-sig'))
            ai_payload = json.loads((tmpdir / 'stage4_selection_ai.json').read_text(encoding='utf-8-sig'))
            llm_payload = json.loads((tmpdir / 'stage4_selection_llm.json').read_text(encoding='utf-8-sig'))
            log_text = (tmpdir / 'stage4_selection_run.log').read_text(encoding='utf-8-sig')
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        self.assertEqual(summary['snapshot']['item_count'], 3)
        self.assertEqual(summary['keyword']['qualified_count'], 2)
        self.assertEqual(summary['semantic']['candidate_count'], 2)
        self.assertEqual(summary['llm']['kept_count'], 1)
        self.assertEqual(summary['ai']['qualified_count'], 1)
        self.assertIn('Stage 4 Selection Review', review_text)
        self.assertIn('规则过滤（Rule Filter）', review_text)
        self.assertIn('语义召回（Semantic Recall）', review_text)
        self.assertIn('LLM 质量闸门（LLM Quality Gate）', review_text)
        self.assertIn('summary: Official OpenAI Agents SDK for Python', review_text)
        self.assertIn('topics: openai, agent, sdk', review_text)
        self.assertEqual(semantic_payload['semantic']['rejected_count'], 1)
        self.assertEqual(semantic_payload['semantic']['topics'][0]['label'], 'AI Agents')
        self.assertEqual(semantic_payload['semantic']['candidates'][1]['summary'], 'Official OpenAI Agents SDK for Python')
        self.assertFalse(ai_payload['skipped'])
        self.assertEqual(ai_payload['selection']['strategy'], 'ai')
        self.assertEqual(ai_payload['selection']['qualified_items'][0]['summary'], 'Agent runtime now supports tool calling and tracing.')
        self.assertEqual(llm_payload['llm']['kept_count'], 1)
        self.assertEqual(llm_payload['llm']['rejected_items'][0]['rejected_stage'], 'llm')
        self.assertEqual(llm_payload['llm']['decisions'][1]['summary'], 'Official OpenAI Agents SDK for Python')
        self.assertIn('language: Python', llm_payload['llm']['decisions'][1]['context_lines'])
        self.assertEqual(log_text, 'stage4 ok')

    def test_export_selection_outbox_records_ai_skip_reason(self):
        snapshot, ai_item, _, _ = self._build_snapshot()
        keyword_selection = SelectionResult(
            strategy='keyword',
            qualified_items=[ai_item],
            selected_new_items=[ai_item],
            total_candidates=3,
            total_selected=1,
        )

        tmpdir = self._create_workspace_tmpdir()
        try:
            export_selection_outbox(
                outbox_dir=tmpdir,
                generated_at=datetime(2026, 4, 19, 10, 31, tzinfo=timezone.utc),
                config_path='config/config.yaml',
                storage_data_dir=Path(tmpdir) / 'stage4_storage',
                snapshot=snapshot,
                keyword_selection=keyword_selection,
                ai_selection=None,
                ai_skip_reason='API_KEY missing',
                run_log='stage4 skip',
            )
            ai_payload = json.loads((tmpdir / 'stage4_selection_ai.json').read_text(encoding='utf-8-sig'))
            llm_payload = json.loads((tmpdir / 'stage4_selection_llm.json').read_text(encoding='utf-8-sig'))
            semantic_payload = json.loads((tmpdir / 'stage4_selection_semantic.json').read_text(encoding='utf-8-sig'))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        self.assertTrue(ai_payload['skipped'])
        self.assertEqual(ai_payload['reason'], 'API_KEY missing')
        self.assertIsNone(ai_payload['selection'])
        self.assertTrue(llm_payload['llm']['skipped'])
        self.assertEqual(llm_payload['llm']['reason'], 'API_KEY missing')
        self.assertTrue(semantic_payload['semantic']['skipped'])
        self.assertEqual(semantic_payload['semantic']['reason'], 'API_KEY missing')


if __name__ == '__main__':
    unittest.main()
