import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from newspulse.utils.logging import configure_logging, get_logger


class LoggingUtilsTest(unittest.TestCase):
    def test_configure_logging_replaces_managed_handlers_without_duplicates(self):
        with TemporaryDirectory() as tmp:
            log_file = Path(tmp) / "logs" / "newspulse.log"
            logger = configure_logging("DEBUG", str(log_file))
            logger = configure_logging("INFO", str(log_file))

            managed_handlers = [
                handler
                for handler in logger.handlers
                if getattr(handler, "_newspulse_handler", False)
            ]
            self.assertEqual(len(managed_handlers), 2)

            child_logger = get_logger("newspulse.tests.logging")
            child_logger.info("logging smoke test")
            for handler in managed_handlers:
                handler.flush()

            self.assertTrue(log_file.exists())
            self.assertIn("logging smoke test", log_file.read_text(encoding="utf-8"))
            configure_logging()


if __name__ == "__main__":
    unittest.main()
