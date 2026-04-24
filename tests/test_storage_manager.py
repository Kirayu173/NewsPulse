import unittest
from tests.helpers.tempdir import WorkspaceTemporaryDirectory as TemporaryDirectory

from newspulse.storage.manager import StorageManager


class StorageManagerFacadeTest(unittest.TestCase):
    def test_storage_manager_exposes_explicit_backend_and_repo_accessors(self):
        with TemporaryDirectory() as tmp:
            storage = StorageManager(
                backend_type="local",
                data_dir=tmp,
                enable_txt=False,
                enable_html=False,
            )
            try:
                self.assertIs(storage.backend, storage.get_backend())
                self.assertIsNotNone(storage.news_repo)
                self.assertIsNotNone(storage.schedule_repo)
                self.assertIsNotNone(storage.ai_filter_repo)
                self.assertIsNotNone(storage.article_content_repo)
            finally:
                storage.cleanup()


if __name__ == "__main__":
    unittest.main()
