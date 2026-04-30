from __future__ import annotations

import os
import unittest
from pathlib import Path

from core.assertions import assert_equal, assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config, timeout_seconds
from core.files import batch_import_file, read_xlsx_rows
from core.logger import setup_logger
from pages.environment_page import EnvironmentPage
from pages.import_page import ImportPage
from pages.login_page import LoginPage


CASE_MODULE = "环境管理"


class TestBatchImportEnvironments(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config(Path("config/config.yaml"))
        cls.logger = setup_logger(cls.config)
        cls.cdp = CDPDriver(cls.config, cls.logger)
        cls.cdp.connect()
        LoginPage(cdp_driver=cls.cdp, config=cls.config).ensure_logged_in_as_config_account()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.cdp.close()

    def test_batch_import_environments(self) -> None:
        import_file = batch_import_file(self.config)
        import_names = self._import_environment_names(import_file)
        assert_true(import_names, f"batch import file has no valid environment rows: {import_file}")
        name_prefix = self._common_prefix(import_names)
        batch_import_timeout = timeout_seconds(self.config, "batch_import_seconds", 120)

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        import_page = ImportPage(cdp_driver=self.cdp, config=self.config)
        imported = False

        try:
            environment_page.open_list()
            self._delete_imported_environments(environment_page, name_prefix)

            import_page.open_batch_import()
            import_page.choose_import_file(import_file)
            import_page.submit_import()
            result_rows = import_page.wait_import_result(
                expected_count=len(import_names),
                timeout_seconds=batch_import_timeout,
            )
            result_text = import_page.read_import_result()
            assert_true(
                "失败: 0 条" in result_text,
                f"batch import result has failed rows: {result_text}",
            )
            assert_equal(
                len(result_rows),
                len(import_names),
                f"batch import result count is incorrect: rows={result_rows}",
            )
            for row in result_rows:
                assert_equal(
                    row.get("result"),
                    "成功",
                    f"batch import row was not successful: {row}",
                )
            import_page.close_import_result()
            imported = True

            environment_page.open_list()
            environment_page.search_environment_without_assert(name_prefix)
            created_names = environment_page.wait_environment_count_by_prefix_in_current_list(
                name_prefix,
                len(import_names),
                timeout_seconds=timeout_seconds(self.config, "search_result_seconds", 10),
            )
            for name in import_names:
                assert_true(
                    name in created_names,
                    f"imported environment was not found in list: name={name}, actual={created_names}",
                )

            environment_page.delete_environments_by_prefix_from_current_list(name_prefix)
            environment_page.search_environment_without_assert(name_prefix)
            assert_true(
                not environment_page.environment_names_by_prefix_in_current_list(name_prefix),
                f"batch imported environments were not deleted: prefix={name_prefix}",
            )
            imported = False
        finally:
            try:
                if imported:
                    environment_page.open_list()
                    self._delete_imported_environments(environment_page, name_prefix)
            except Exception:
                pass
            try:
                environment_page.clear_search()
            except Exception:
                pass

    def _import_environment_names(self, file_path: Path) -> list[str]:
        names: list[str] = []
        for row in read_xlsx_rows(file_path):
            name = str(row.get("环境名称") or "").strip()
            if not name:
                continue
            if name.startswith("选填") or name.startswith("说明"):
                continue
            names.append(name)
        return names

    def _common_prefix(self, names: list[str]) -> str:
        prefix = os.path.commonprefix(names).strip()
        if prefix:
            return prefix
        return names[0]

    def _delete_imported_environments(self, environment_page: EnvironmentPage, name_prefix: str) -> None:
        environment_page.search_environment_without_assert(name_prefix)
        environment_page.delete_environments_by_prefix_from_current_list(name_prefix)
        environment_page.wait_no_environment_by_prefix_in_current_list(name_prefix)
        environment_page.clear_search()


if __name__ == "__main__":
    unittest.main()
