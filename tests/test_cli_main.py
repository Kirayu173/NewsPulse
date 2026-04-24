import unittest
from unittest.mock import patch

from newspulse.cli.errors import build_cli_error_guidance
from newspulse.cli.main import build_parser, main
from newspulse.core.preflight import PreflightReport
from newspulse.workflow.shared.ai_runtime.errors import PromptTemplateNotFoundError


class CLIMainTest(unittest.TestCase):
    def test_parser_supports_default_run_and_subcommands(self):
        parser = build_parser()

        self.assertEqual(parser.parse_args([]).command, None)
        self.assertEqual(parser.parse_args(["run"]).command, "run")
        self.assertEqual(parser.parse_args(["doctor"]).command, "doctor")
        self.assertEqual(parser.parse_args(["status"]).command, "status")
        self.assertEqual(parser.parse_args(["test-notification"]).command, "test-notification")

    def test_main_runs_doctor_subcommand(self):
        with patch("newspulse.cli.main.run_doctor", return_value=True) as run_doctor:
            exit_code = main(["doctor"])

        self.assertEqual(exit_code, 0)
        run_doctor.assert_called_once_with()

    def test_main_runs_status_subcommand(self):
        with (
            patch("newspulse.cli.main.load_config", return_value={"DEBUG": False}) as load_config,
            patch("newspulse.cli.main.handle_status_commands") as handle_status_commands,
        ):
            exit_code = main(["status"])

        self.assertEqual(exit_code, 0)
        load_config.assert_called_once_with()
        handle_status_commands.assert_called_once_with({"DEBUG": False})

    def test_main_blocks_workflow_when_startup_preflight_fails(self):
        report = PreflightReport(mode="startup", config_path="config/config.yaml")
        report.add("fail", "Config file", "missing")

        with (
            patch("newspulse.cli.main.run_preflight", return_value=report) as run_preflight,
            patch("newspulse.cli.main.NewsRunner") as runner_cls,
        ):
            exit_code = main(["run"])

        self.assertEqual(exit_code, 1)
        run_preflight.assert_called_once_with(mode="startup")
        runner_cls.assert_not_called()

    def test_main_runs_workflow_after_startup_preflight_passes(self):
        report = PreflightReport(
            mode="startup",
            config_path="config/config.yaml",
            config={"VERSION_CHECK_URL": "", "CONFIGS_VERSION_CHECK_URL": ""},
        )

        with (
            patch("newspulse.cli.main.run_preflight", return_value=report),
            patch("newspulse.cli.main.NewsRunner") as runner_cls,
        ):
            exit_code = main(["run"])

        self.assertEqual(exit_code, 0)
        runner_cls.assert_called_once_with(config=report.config)
        runner_cls.return_value.run.assert_called_once_with()


class CLIErrorGuidanceTest(unittest.TestCase):
    def test_build_cli_error_guidance_surfaces_prompt_fix_steps(self):
        guidance = build_cli_error_guidance(
            PromptTemplateNotFoundError(
                "prompt missing",
                details={"path": "config/ai_filter/prompt.txt"},
            )
        )

        self.assertEqual(guidance.title, "AI prompt 文件缺失")
        self.assertIn("newspulse doctor", " ".join(guidance.fixes))
        self.assertEqual(guidance.references, ("config/ai_filter/prompt.txt",))


if __name__ == "__main__":
    unittest.main()
