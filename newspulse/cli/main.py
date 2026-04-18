# coding=utf-8
"""CLI entrypoint orchestration."""

import argparse

from newspulse import __version__
from newspulse.cli.common import configure_console_output
from newspulse.cli.doctor import run_doctor
from newspulse.cli.status import handle_status_commands
from newspulse.cli.test_notification import run_test_notification
from newspulse.cli.versioning import check_all_versions
from newspulse.core import load_config
from newspulse.core.config_paths import get_config_layout, resolve_frequency_words_path
from newspulse.runner import NewsRunner


def main() -> None:
    """Program entrypoint."""
    configure_console_output()
    parser = argparse.ArgumentParser(
        description="NewsPulse - hotlist aggregation and analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Status:
  --show-schedule        Show resolved scheduler status
Checks:
  --doctor               Run environment and config checks
  --test-notification    Send a test notification

Examples:
  python -m newspulse                     # run normally
  python -m newspulse --show-schedule     # inspect schedule
  python -m newspulse --doctor            # run checks
  python -m newspulse --test-notification # test notification path
""",
    )
    parser.add_argument("--show-schedule", action="store_true", help="show scheduler status")
    parser.add_argument("--doctor", action="store_true", help="run environment checks")
    parser.add_argument(
        "--test-notification",
        action="store_true",
        help="send a test notification",
    )

    args = parser.parse_args()

    debug_mode = False
    try:
        if args.doctor:
            ok = run_doctor()
            if not ok:
                raise SystemExit(1)
            return

        config = load_config()

        if args.show_schedule:
            handle_status_commands(config)
            return

        if args.test_notification:
            ok = run_test_notification(config)
            if not ok:
                raise SystemExit(1)
            return

        version_url = config.get("VERSION_CHECK_URL", "")
        configs_version_url = config.get("CONFIGS_VERSION_CHECK_URL", "")

        need_update = False
        remote_version = None
        if version_url:
            need_update, remote_version = check_all_versions(
                version_url,
                configs_version_url,
            )

        runner = NewsRunner(config=config)
        if runner.is_github_actions and need_update and remote_version:
            runner.update_info = {
                "current_version": __version__,
                "remote_version": remote_version,
            }

        debug_mode = runner.ctx.config.get("DEBUG", False)
        runner.run()
    except FileNotFoundError as e:
        layout = get_config_layout()
        print(f"Config file error: {e}")
        print("\nRequired files:")
        print(f"  - {layout.config_path}")
        print(f"  - {resolve_frequency_words_path(config_root=layout.config_root)}")
        print("\nPlease update your local config before running again.")
    except Exception as e:
        print(f"Runtime error: {e}")
        if debug_mode:
            raise
