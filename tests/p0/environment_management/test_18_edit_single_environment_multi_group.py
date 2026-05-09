from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from pages.environment_page import EnvironmentPage
from pages.login_page import LoginPage


CASE_MODULE = "环境管理"


class TestEditSingleEnvironmentMultiGroup(unittest.TestCase):
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

    def test_edit_single_environment_multi_group_and_restore(self) -> None:
        data = self.config["test_data"]["environment_edit_single_multi_group"]
        group_name = str(data.get("group_name", "分组二")).strip()
        assert_true(group_name, "single environment multi group edit test has no group name configured")

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        original_serial = ""
        original_groups: list[str] = []
        group_added = False

        try:
            environment_page.open_list()
            original_serial = environment_page.first_environment_serial()
            assert_true(bool(original_serial), "first environment serial is empty")

            original_groups, edited_groups = environment_page.edit_environment_groups_by_serial(
                original_serial,
                add_groups=[group_name],
            )
            group_added = group_name not in original_groups
            assert_true(
                group_name in edited_groups,
                f"group was not selected in edit drawer: serial={original_serial}, groups={edited_groups}",
            )

            environment_page.wait_environment_by_serial_visible(original_serial)
            edited_group_text = environment_page.environment_group_full_text_by_serial(original_serial)
            for expected_group in self._unique_non_empty(original_groups + [group_name]):
                assert_true(
                    expected_group in edited_group_text,
                    "environment group was not changed successfully: "
                    f"serial={original_serial}, expected_group={expected_group}, actual={edited_group_text}",
                )

            _, restored_groups = environment_page.edit_environment_groups_by_serial(
                original_serial,
                remove_groups=[group_name],
            )
            group_added = False
            assert_true(
                group_name not in restored_groups,
                f"group was not deselected in edit drawer: serial={original_serial}, groups={restored_groups}",
            )

            environment_page.wait_environment_by_serial_visible(original_serial)
            restored_group_text = environment_page.environment_group_full_text_by_serial(original_serial)
            assert_true(
                group_name not in restored_group_text,
                "environment group was not restored successfully: "
                f"serial={original_serial}, removed_group={group_name}, actual={restored_group_text}",
            )
            for expected_group in original_groups:
                assert_true(
                    expected_group in restored_group_text,
                    "original environment group was not preserved after restore: "
                    f"serial={original_serial}, expected_group={expected_group}, actual={restored_group_text}",
                )
        finally:
            if group_added and original_serial:
                try:
                    environment_page.edit_environment_groups_by_serial(
                        original_serial,
                        remove_groups=[group_name],
                    )
                except Exception:
                    pass
            try:
                environment_page.clear_search()
            except Exception:
                pass

    def _unique_non_empty(self, values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            text = str(value).strip()
            if text and text not in result:
                result.append(text)
        return result


if __name__ == "__main__":
    unittest.main()
