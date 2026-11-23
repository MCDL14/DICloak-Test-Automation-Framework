from __future__ import annotations

import json
import re
import unittest
from itertools import count
from unittest import mock

from pages.personal_settings_page import PersonalSettingsPage


class PersonalKernelDownloadTests(unittest.TestCase):
    def page(self, records):
        page = object.__new__(PersonalSettingsPage)
        page.config = {"timeouts": {"kernel_download_seconds": 1}}
        page.cdp = mock.MagicMock()
        page.open_download_record_kernel_tab = mock.Mock()
        page.refresh_download_record_kernels = mock.Mock()
        page._download_record_kernel_states = mock.Mock(side_effect=lambda: list(records))

        def delete(script):
            match = re.search(r"const expectedVersion = (.*?);", script)
            self.assertIsNotNone(match)
            version = json.loads(match.group(1))
            for index, record in enumerate(records):
                if record["version"] == version:
                    records.pop(index)
                    return
            self.fail("Deletion selected a kernel absent from the record list")

        page.cdp.click_element_by_script.side_effect = delete
        return page

    def test_missing_major_skips_deletion(self):
        records = [{"version": "152.1.2", "deletable": True}]
        page = self.page(records)
        self.assertEqual(page.delete_downloaded_kernels("142"), [])
        page.cdp.click_element_by_script.assert_not_called()
        self.assertEqual(records[0]["version"], "152.1.2")

    def test_deletes_only_target_major_including_first_record(self):
        for major, other in (("142", "152"), ("152", "142")):
            with self.subTest(major=major):
                records = [
                    {"version": f"{major}.1.19", "deletable": True},
                    {"version": f"{other}.1.2", "deletable": True},
                    {"version": f"{major}.1.12", "deletable": True},
                    {"version": "134.1.28", "deletable": True},
                    {"version": f"{major}.1.11", "deletable": True},
                ]
                page = self.page(records)
                self.assertEqual(
                    page.delete_downloaded_kernels(major),
                    [f"{major}.1.19", f"{major}.1.12", f"{major}.1.11"],
                )
                self.assertEqual([r["version"] for r in records], [f"{other}.1.2", "134.1.28"])
                self.assertEqual(page.cdp.click_element_by_script.call_count, 3)
                self.assertGreaterEqual(page.refresh_download_record_kernels.call_count, 4)

    def test_refresh_reveals_old_version_after_deletion_temporarily_empties_rows(self):
        for major in ("142", "152"):
            with self.subTest(major=major):
                installed = [
                    {"version": f"{major}.1.19", "deletable": True},
                    {"version": f"{major}.1.12", "deletable": True},
                ]
                records = [installed[0]]
                deleted = []
                page = self.page(records)

                def refresh():
                    records[:] = installed[:1]

                def delete(script):
                    version = json.loads(re.search(r"const expectedVersion = (.*?);", script).group(1))
                    self.assertEqual(version, installed[0]["version"])
                    deleted.append(version)
                    installed.pop(0)
                    records.clear()

                page.refresh_download_record_kernels.side_effect = refresh
                page.cdp.click_element_by_script.side_effect = delete
                self.assertEqual(page.delete_downloaded_kernels(major), [f"{major}.1.19", f"{major}.1.12"])
                self.assertEqual(deleted, [f"{major}.1.19", f"{major}.1.12"])
                self.assertEqual(installed, [])
                self.assertGreaterEqual(page.refresh_download_record_kernels.call_count, 3)

    def test_initial_refresh_reloads_all_installed_versions_before_checking_for_missing_major(self):
        for initial_empty in (True, False):
            with self.subTest(initial_empty=initial_empty):
                installed = [
                    {"version": "142.1.19", "deletable": True},
                    {"version": "152.1.3", "deletable": True},
                    {"version": "142.1.12", "deletable": True},
                ]
                records = [] if initial_empty else [installed[0]]
                page = self.page(records)

                def refresh():
                    if page.refresh_download_record_kernels.call_count == 1:
                        records[:] = installed

                page.refresh_download_record_kernels.side_effect = refresh
                self.assertEqual(page.delete_downloaded_kernels("142"), ["142.1.19", "142.1.12"])
                self.assertEqual([r["version"] for r in records], ["152.1.3"])
                self.assertEqual(page.cdp.click_element_by_script.call_count, 2)

    def test_target_reappearing_on_refresh_is_waited_for_without_clicking_delete_again(self):
        target = {"version": "142.1.19", "deletable": True}
        records = [target]
        page = self.page(records)

        def refresh():
            if page.refresh_download_record_kernels.call_count == 2:
                records[:] = [target]

        page.refresh_download_record_kernels.side_effect = refresh
        page.cdp.click_element_by_script.side_effect = lambda script: records.clear()
        with mock.patch("pages.personal_settings_page.time.monotonic", side_effect=count(0, 0.1)), mock.patch(
            "pages.personal_settings_page.time.sleep", side_effect=lambda interval: records.clear()
        ) as sleep:
            self.assertEqual(page.delete_downloaded_kernels("142"), ["142.1.19"])
        self.assertEqual(records, [])
        page.cdp.click_element_by_script.assert_called_once()
        self.assertEqual(page.refresh_download_record_kernels.call_count, 3)
        sleep.assert_called_once_with(0.2)

    def test_disappearance_of_another_version_does_not_confirm_target_deletion(self):
        records = [
            {"version": "142.1.19", "deletable": True},
            {"version": "142.1.12", "deletable": True},
        ]
        page = self.page(records)

        def remove_other_version(script):
            self.assertIn('const expectedVersion = "142.1.19";', script)
            records[:] = [record for record in records if record["version"] == "142.1.19"]

        page.cdp.click_element_by_script.side_effect = remove_other_version
        with mock.patch("pages.personal_settings_page.time.monotonic", side_effect=count(0, 0.2)), mock.patch(
            "pages.personal_settings_page.time.sleep"
        ):
            with self.assertRaisesRegex(TimeoutError, "142.1.19"):
                page.delete_downloaded_kernels("142")
        page.cdp.click_element_by_script.assert_called_once()
        self.assertEqual([r["version"] for r in records], ["142.1.19"])

    def test_undeletable_or_active_kernel_is_reported(self):
        for extra in ({"deletable": False}, {"deletable": True, "busy": True}):
            with self.subTest(extra=extra):
                page = self.page([{"version": "142.1.12", **extra}])
                with self.assertRaisesRegex(RuntimeError, "不可删除"):
                    page.delete_downloaded_kernels("142")
                page.cdp.click_element_by_script.assert_not_called()

    def test_deletion_must_be_confirmed_in_record_list(self):
        page = self.page([{"version": "142.1.12", "deletable": True}])
        page.cdp.click_element_by_script.side_effect = None
        with mock.patch("pages.personal_settings_page.time.monotonic", side_effect=count(0, 0.2)), mock.patch(
            "pages.personal_settings_page.time.sleep"
        ):
            with self.assertRaisesRegex(TimeoutError, "删除后仍出现在下载记录"):
                page.delete_downloaded_kernels("142")

    def test_refresh_clicks_the_download_record_icon_and_waits_until_idle(self):
        page = self.page([])
        del page.refresh_download_record_kernels
        page.cdp.click_element_by_script.side_effect = None
        page.cdp.evaluate.side_effect = [False, False, True]
        with mock.patch("pages.personal_settings_page.time.monotonic", side_effect=count(0, 0.1)), mock.patch(
            "pages.personal_settings_page.time.sleep"
        ) as sleep:
            page.refresh_download_record_kernels()
        page.cdp.click_element_by_script.assert_called_once()
        script = page.cdp.click_element_by_script.call_args.args[0]
        self.assertIn("#DownloadLog", script)
        self.assertIn(".el-icon.tw-cursor-pointer", script)
        self.assertEqual(page.cdp.evaluate.call_count, 3)
        self.assertIn("tw-animate-spin", page.cdp.evaluate.call_args.args[0])
        self.assertEqual(sleep.call_args_list, [mock.call(0.1), mock.call(0.1)])
        self.assertEqual(page.cdp.method_calls[0], mock.call.click_element_by_script(script))

    def test_refresh_that_never_becomes_idle_times_out(self):
        page = self.page([])
        del page.refresh_download_record_kernels
        page.config["timeouts"]["page_seconds"] = 1
        page.cdp.click_element_by_script.side_effect = None
        page.cdp.evaluate.return_value = False
        with mock.patch("pages.personal_settings_page.time.monotonic", side_effect=count(0, 0.2)), mock.patch(
            "pages.personal_settings_page.time.sleep"
        ):
            with self.assertRaisesRegex(TimeoutError, "内核下载记录刷新完成超时"):
                page.refresh_download_record_kernels()
        page.cdp.click_element_by_script.assert_called_once()
        self.assertGreater(page.cdp.evaluate.call_count, 0)

    def test_download_waits_through_partial_record(self):
        page = self.page([])
        page._download_record_kernel_states.side_effect = [
            [{"version": "142.1.12", "deletable": True, "busy": True}],
            [{"version": "142.1.12", "deletable": True, "busy": False}],
        ]
        with mock.patch("pages.personal_settings_page.time.sleep"):
            page.wait_kernel_download_completed("142", "142.1.12", timeout_seconds=1)
        self.assertEqual(page._download_record_kernel_states.call_count, 2)

    def test_failed_download_is_assertion_failure(self):
        page = self.page([{"version": "152.1.2", "failed": True}])
        with self.assertRaisesRegex(AssertionError, "下载失败"):
            page.wait_kernel_download_completed("152", "152.1.2", timeout_seconds=1)

    def test_download_timeout_does_not_accept_another_major(self):
        page = self.page([{"version": "142.1.12", "deletable": True}])
        with mock.patch("pages.personal_settings_page.time.monotonic", side_effect=[0, 0, 2]), mock.patch(
            "pages.personal_settings_page.time.sleep"
        ):
            with self.assertRaisesRegex(TimeoutError, "152.1.2"):
                page.wait_kernel_download_completed("152", "152.1.2", timeout_seconds=1)

    def test_rejects_invalid_major_and_mismatched_version(self):
        page = self.page([])
        with self.assertRaises(ValueError):
            page.delete_downloaded_kernels("142 || 152")
        with self.assertRaises(ValueError):
            page.wait_kernel_download_completed("142", "152.1.2", timeout_seconds=1)
        page.cdp.click_element_by_script.assert_not_called()


if __name__ == "__main__":
    unittest.main()
