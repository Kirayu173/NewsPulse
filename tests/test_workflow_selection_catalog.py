import unittest

from newspulse.workflow.selection.catalog import build_runtime_topics, parse_topic_catalog, topics_to_tag_rows
from newspulse.workflow.selection.models import AIActiveTag


class TopicCatalogTest(unittest.TestCase):
    def test_parse_topic_catalog_supports_structured_sections(self):
        topics = parse_topic_catalog(
            """
            # comment
            [TOPIC_CATALOG]

            [AI Agent / MCP]
            AI Agent、MCP 与智能工作流
            + AI Agent
            + MCP
            - 教程
            @priority: 1

            [中国科技]
            DeepSeek、阿里、腾讯、华为、小米
            + DeepSeek
            + 腾讯
            @priority: 2
            """
        )

        self.assertEqual([topic.label for topic in topics], ["AI Agent / MCP", "中国科技"])
        self.assertEqual(topics[0].seed_keywords, ("AI Agent", "MCP"))
        self.assertEqual(topics[0].negative_keywords, ("教程",))
        self.assertEqual(topics[1].description, "DeepSeek、阿里、腾讯、华为、小米")

    def test_parse_topic_catalog_falls_back_to_numbered_outline(self):
        topics = parse_topic_catalog(
            """
            1. 中国科技：DeepSeek、腾讯、字节与中国科技平台
            2. 全球科技巨头：OpenAI、Google、Microsoft、Apple
            """
        )

        self.assertEqual([topic.label for topic in topics], ["中国科技", "全球科技巨头"])
        self.assertEqual(topics[0].priority, 1)
        self.assertEqual(topics[1].source, "interests_outline")

    def test_build_runtime_topics_merges_active_tag_ids_with_catalog_details(self):
        runtime_topics = build_runtime_topics(
            [
                AIActiveTag(id=8, tag="AI Agent / MCP", description="legacy", priority=3),
                AIActiveTag(id=9, tag="中国科技", description="legacy cn", priority=4),
            ],
            parse_topic_catalog(
                """
                [TOPIC_CATALOG]

                [AI Agent / MCP]
                AI Agent、MCP 与智能工作流
                + MCP
                @priority: 1

                [中国科技]
                DeepSeek 与中国科技平台
                + DeepSeek
                @priority: 2
                """
            ),
        )

        self.assertEqual([topic.topic_id for topic in runtime_topics], [8, 9])
        self.assertEqual(runtime_topics[0].seed_keywords, ("MCP",))
        self.assertEqual(runtime_topics[1].description, "DeepSeek 与中国科技平台")

    def test_topics_to_tag_rows_keeps_priority_order(self):
        rows = topics_to_tag_rows(
            parse_topic_catalog(
                """
                [TOPIC_CATALOG]

                [B]
                desc
                @priority: 2

                [A]
                desc
                @priority: 1
                """
            )
        )

        self.assertEqual([row["tag"] for row in rows], ["A", "B"])
        self.assertEqual([row["priority"] for row in rows], [1, 2])


if __name__ == "__main__":
    unittest.main()
