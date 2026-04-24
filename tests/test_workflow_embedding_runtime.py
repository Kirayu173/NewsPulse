import unittest
from types import SimpleNamespace

from newspulse.workflow.shared.ai_runtime.embedding import EmbeddingRuntimeClient


class EmbeddingRuntimeClientTest(unittest.TestCase):
    def test_embed_texts_splits_large_requests_into_batches(self):
        calls: list[list[str]] = []

        class FakeClient:
            def __init__(self, **kwargs):
                self.embeddings = SimpleNamespace(create=self.create)

            def create(self, **params):
                inputs = list(params["input"])
                calls.append(inputs)
                return SimpleNamespace(
                    data=[
                        SimpleNamespace(embedding=[float(len(text)), float(index)])
                        for index, text in enumerate(inputs)
                    ],
                    usage=None,
                )

        client = EmbeddingRuntimeClient(
            {
                "MODEL": "openai/embedding-test",
                "API_KEY": "dummy-key",
                "BATCH_SIZE": 2,
            },
            openai_client_factory=FakeClient,
        )

        result = client.embed_texts(["a", "bb", "ccc", "dddd", "eeeee"])

        self.assertEqual([len(batch) for batch in calls], [2, 2, 1])
        self.assertEqual(len(result.vectors), 5)
        self.assertEqual(result.vectors[0], (1.0, 0.0))
        self.assertEqual(result.vectors[4], (5.0, 0.0))


if __name__ == "__main__":
    unittest.main()
