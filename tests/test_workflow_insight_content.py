import unittest

from newspulse.workflow.insight.content_enricher import ContentFetchEnricher
from newspulse.workflow.insight.content_models import FetchedContent
from newspulse.workflow.insight.content_preprocessor import ContentPreprocessor
from newspulse.workflow.insight.models import (
    InsightNewsContext,
    InsightRankSignals,
    InsightSelectionEvidence,
    InsightSourceContext,
)


class FakeResponse:
    status_code = 200
    headers = {"content-type": "text/html; charset=utf-8"}

    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        return None


class FakeHttpClient:
    def __init__(self, html: str):
        self.html = html
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        return FakeResponse(self.html)


def _context() -> InsightNewsContext:
    return InsightNewsContext(
        news_item_id="1",
        title="OpenAI ships agent runtime",
        source_id="hackernews",
        source_name="Hacker News",
        url="https://example.com/story",
        rank_signals=InsightRankSignals(current_rank=1, rank_trend="up"),
        source_context=InsightSourceContext(
            source_kind="article",
            summary="Structured source summary.",
            attributes=("host: example.com", "route: article_content"),
        ),
        selection_evidence=InsightSelectionEvidence(
            matched_topics=("AI Agents",),
            quality_score=0.9,
            llm_reasons=("agent runtime signal",),
        ),
    )


class ContentEnrichmentTest(unittest.TestCase):
    def test_fetch_many_extracts_article_text_with_lightweight_adapter(self):
        html = """
        <html><head><title>Story</title></head><body>
        <nav>menu / menu / menu / menu / menu / menu</nav>
        <article>
        <p>OpenAI shipped a new agent runtime for developer workflows with concrete deployment details.</p>
        <p>The release matters because teams can integrate tool use, patches, and verification in one loop.</p>
        </article>
        </body></html>
        """
        client = FakeHttpClient(html)
        enricher = ContentFetchEnricher(
            enabled=True,
            extractor_order=["beautifulsoup"],
            client=client,
        )

        fetched, diagnostics = enricher.fetch_many([_context()], max_workers=1)

        self.assertEqual(diagnostics["success_count"], 1)
        self.assertEqual(fetched["1"].status, "ok")
        self.assertEqual(fetched["1"].extraction_method, "beautifulsoup")
        self.assertIn("agent runtime", fetched["1"].text)

    def test_preprocessor_reduces_long_text_dedupes_and_respects_budget(self):
        paragraph = (
            "OpenAI shipped an agent runtime for developer workflows. "
            "The article explains tool use, patches, verification, and production rollout details."
        )
        fetched = FetchedContent(
            news_item_id="1",
            url="https://example.com/story",
            status="ok",
            excerpt="Agent runtime release.",
            text="\n\n".join([paragraph, paragraph, "cookie privacy policy accept all", paragraph * 8]),
            extraction_method="beautifulsoup",
        )
        preprocessor = ContentPreprocessor()

        reduced, diagnostics = preprocessor.reduce_many({"1": _context()}.values(), {"1": fetched}, max_chars=260)

        self.assertEqual(len(reduced), 1)
        self.assertLessEqual(reduced[0].reduced_char_count, 260)
        self.assertEqual(diagnostics["context_count"], 1)
        self.assertEqual(reduced[0].diagnostics["deduped_paragraph_count"], 2)
        self.assertTrue(reduced[0].diagnostics["used_fetched_content"])
        self.assertNotIn("cookie privacy", reduced[0].reduced_text.lower())

    def test_preprocessor_falls_back_to_structured_context_when_fetch_fails(self):
        failed = FetchedContent(
            news_item_id="1",
            url="https://example.com/story",
            status="failed",
            diagnostics={"reason": "timeout"},
        )
        reduced = ContentPreprocessor().reduce(_context(), failed, max_chars=200)

        self.assertEqual(reduced.source_summary, "Structured source summary.")
        self.assertEqual(reduced.key_paragraphs, [])
        self.assertEqual(reduced.diagnostics["fetch_status"], "failed")
        self.assertFalse(reduced.diagnostics["used_fetched_content"])


if __name__ == "__main__":
    unittest.main()
