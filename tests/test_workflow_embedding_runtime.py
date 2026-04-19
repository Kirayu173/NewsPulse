import unittest

from newspulse.workflow.shared.ai_runtime.embedding import EmbeddingRuntimeClient


class EmbeddingRuntimeClientTest(unittest.TestCase):
    def test_embed_texts_splits_large_requests_into_batches(self):
        calls: list[list[str]] = []

        def fake_embedding(**params):
            inputs = list(params["input"])
            calls.append(inputs)
            return {
                "data": [
                    {"index": index, "embedding": [float(len(text)), float(index)]}
                    for index, text in enumerate(inputs)
                ]
            }

        client = EmbeddingRuntimeClient(
            {
                "MODEL": "openai/embedding-test",
                "API_KEY": "dummy-key",
                "BATCH_SIZE": 2,
            },
            embedding_func=fake_embedding,
        )

        rows = client.embed_texts(["a", "bb", "ccc", "dddd", "eeeee"])

        self.assertEqual([len(batch) for batch in calls], [2, 2, 1])
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0], [1.0, 0.0])
        self.assertEqual(rows[4], [5.0, 0.0])


if __name__ == "__main__":
    unittest.main()
