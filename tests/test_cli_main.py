import unittest
from unittest.mock import patch

from newspulse.cli.errors import build_cli_error_guidance
from newspulse.cli.main import build_parser, main, resolve_command
from newspulse.core.preflight import PreflightReport
from newspulse.workflow.shared.ai_runtime.errors import PromptTemplateNotFoundError


class CLIMainTest(unittest.TestCase):
    def test_resolve_command_supports_subcommands_and_legacy_flags(self):
        parser = build_parser()

        self.assertEqual(resolve_command(parser.parse_args([])), "run")
        self.assertEqual(resolve_command(parser.parse_args(["run"])), "run")
        self.assertEqual(resolve_command(parser.parse_args(["doctor"])), "doctor")
        self.assertEqual(resolve_command(parser.parse_args(["status"])), "status")
        self.assertEqual(resolve_command(parser.parse_args(["test-notification"])), "test-notification")
        self.assertEqual(resolve_command(parser.parse_args(["--doctor"])), "doctor")
        self.assertEqual(resolve_command(parser.parse_args(["--show-schedule"])), "status")
        self.assertEqual(resolve_command(parser.parse_args(["--test-notification"])), "test-notification")

    def test_main_runs_doctor_subcommand(self):
        with patch("newspulse.cli.main.run_doctor", return_value=True) as run_doctor:
            exit_code = main(["doctor"])

        self.assertEqual(exit_code, 0)
        run_doctor.assert_called_once_with()

    def test_main_routes_legacy_show_schedule_flag(self):
        with (
            patch("newspulse.cli.main.load_config", return_value={"DEBUG": False}) as load_config,
            patch("newspulse.cli.main.handle_status_commands") as handle_status_commands,
        ):
            exit_code = main(["--show-schedule"])

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
