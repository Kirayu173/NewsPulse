import unittest

from newspulse.workflow.shared.scoring import calculate_news_weight


class ScoringHelperTest(unittest.TestCase):
    def test_calculate_news_weight_uses_default_weights_and_unique_ranks(self):
        score = calculate_news_weight(
            {"ranks": [1, 2, 2, 0], "count": 3},
            rank_threshold=3,
            weight_config={},
        )

        self.assertAlmostEqual(score, 76.0)

    def test_calculate_news_weight_falls_back_to_rank_and_ignores_invalid_weights(self):
        score = calculate_news_weight(
            {"ranks": ["bad", -1], "rank": "5", "count": "2"},
            rank_threshold=3,
            weight_config={
                "RANK_WEIGHT": "invalid",
                "FREQUENCY_WEIGHT": 0.5,
                "HOTNESS_WEIGHT": 0.25,
            },
        )

        self.assertAlmostEqual(score, 46.0)


if __name__ == "__main__":
    unittest.main()
