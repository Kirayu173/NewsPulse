import unittest

from newspulse.runner.runtime import detect_runner_environment, resolve_mode_strategy


class RunnerRuntimeHelperTest(unittest.TestCase):
    def test_detect_runner_environment_honors_github_and_docker_flags(self):
        environment = detect_runner_environment(
            {
                "GITHUB_ACTIONS": "true",
                "DOCKER_CONTAINER": "true",
            },
            path_exists=lambda _: False,
        )

        self.assertTrue(environment.is_github_actions)
        self.assertTrue(environment.is_docker_container)
        self.assertFalse(environment.should_open_browser)

    def test_resolve_mode_strategy_falls_back_to_daily(self):
        strategy = resolve_mode_strategy("unknown")

        self.assertEqual(strategy.mode, "daily")
        self.assertEqual(strategy.report_type, "每日报告")


if __name__ == "__main__":
    unittest.main()
