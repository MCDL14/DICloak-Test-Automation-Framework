from __future__ import annotations

import json
import re
import shutil
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from itertools import count
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from core import kernel_cache
from pages.personal_settings_page import PersonalSettingsPage
from tests.p0.environment_management import kernel_download_case as flow
from tests.p0.environment_management import test_01_download_142_kernel as case142
from tests.p0.environment_management import test_01_download_152_kernel as case152


class KernelDownloadCaseTests(unittest.TestCase):
    @contextmanager
    def configured_flow(self, major: str = "142", *, downloaded_before: bool = True, executable: bool = True):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            # Keep both the configured cache and the macOS sibling candidate isolated.
            root = Path(directory) / "cache"
            browsers = root / "browsers"
            previous = browsers / f"{major}.1.1"
            latest = browsers / f"{major}.1.12"
            binary = latest / "core" / "ginsbrowser"
            if downloaded_before:
                previous.mkdir(parents=True)
                (previous / "ginsbrowser").write_bytes(b"old kernel")
            events: list[str] = []
            state = {"visible": False, "action": "打开"}
            settings = mock.MagicMock()
            environment = mock.MagicMock()
            settings.open_from_avatar.side_effect = lambda: events.append("personal_settings")
            settings.open_basic_settings.side_effect = lambda: events.append("basic_settings")
            settings.environment_cache_dir.return_value = root
            settings.download_record_kernel_versions.return_value = []

            def delete_kernel(version):
                self.assertEqual(version, major)
                events.append("delete_kernel")
                if downloaded_before:
                    shutil.rmtree(previous)
                return [previous.name] if downloaded_before else []

            def download_kernel(version):
                self.assertEqual(version, major)
                self.assertFalse(previous.exists())
                events.append("download_kernel")
                binary.parent.mkdir(parents=True)
                if executable:
                    binary.write_bytes(b"new kernel")
                return latest.name

            def create_environment(name, label):
                self.assertEqual(label, f"ChromeBrowser {major}")
                events.append("create_environment")
                state["visible"] = True

            def open_environment(name):
                events.append("open_environment")
                state["action"] = "关闭"
                return 4321

            def close_environment(name, action):
                self.assertEqual(action, "关闭")
                events.append("close_environment")
                state["action"] = "打开"

            def delete_environment(name):
                events.append("delete_environment")
                state["visible"] = False

            settings.delete_downloaded_kernels.side_effect = delete_kernel
            settings.download_latest_kernel.side_effect = download_kernel
            settings.wait_kernel_download_completed.side_effect = lambda *args, **kwargs: events.append("download_completed")
            environment.create_environment_with_kernel.side_effect = create_environment
            environment.open_environment_and_capture_pid.side_effect = open_environment
            environment.click_environment_action.side_effect = close_environment
            environment.delete_environment_from_current_list.side_effect = delete_environment
            environment.environment_visible_in_current_list.side_effect = lambda name: state["visible"]
            environment.environment_action_text.side_effect = lambda name: state["action"]
            patches = {
                "PersonalSettingsPage": {"return_value": settings},
                "EnvironmentPage": {"return_value": environment},
                "resolve_kernel_browsers_dir": {"return_value": browsers},
                "resolve_app_config": {"return_value": SimpleNamespace(browser_process_name="ginsbrowser")},
                "wait_for_kernel_executable_dir": {"return_value": latest},
                "wait_for_pid_running": {"return_value": True},
                "wait_for_pid_stopped": {"return_value": True},
                "resolve_kernel_runtime": {"return_value": SimpleNamespace(cdp_port=18888, command_line="")},
                "kernel_version_from_cdp": {"return_value": f"{major}.0.1"},
                "kernel_version_from_command_line": {"return_value": ""},
                "process_executable_path_by_pid": {"return_value": str(binary)},
            }
            mocked = {name: stack.enter_context(mock.patch.object(flow, name, **kwargs)) for name, kwargs in patches.items()}
            case_type = case142.TestDownload142Kernel if major == "142" else case152.TestDownload152Kernel
            case = case_type("runTest")
            case.config = {}
            case.cdp = object()
            case.logger = mock.MagicMock()
            yield SimpleNamespace(
                case=case,
                settings=settings,
                environment=environment,
                events=events,
                mocked=mocked,
                root=root,
                browsers=browsers,
                previous=previous,
                latest=latest,
                binary=binary,
                state=state,
            )

    def test_both_download_cases_verify_download_before_creating_and_launching(self):
        for major in ("142", "152"):
            for downloaded_before in (False, True):
                with self.subTest(major=major, downloaded_before=downloaded_before):
                    with self.configured_flow(major, downloaded_before=downloaded_before) as run:
                        method = getattr(run.case, f"test_download_{major}_kernel_and_verify_environment")
                        method()
                        self.assertEqual(
                            run.events,
                            [
                                "personal_settings",
                                "basic_settings",
                                "delete_kernel",
                                "download_kernel",
                                "download_completed",
                                "create_environment",
                                "open_environment",
                                "close_environment",
                                "delete_environment",
                            ],
                        )
                        run.settings.wait_kernel_download_completed.assert_called_once_with(
                            major, run.latest.name, timeout_seconds=300
                        )
                        self.assertEqual(run.settings.download_record_kernel_versions.call_count, int(downloaded_before))
                        run.mocked["wait_for_pid_stopped"].assert_called_once_with(4321, timeout_seconds=90)
                        self.assertFalse(run.state["visible"])
                        self.assertEqual(run.environment.clear_search.call_count, 2)

    def test_missing_downloaded_executable_stops_before_environment_creation(self):
        with self.configured_flow(executable=False) as run:
            with self.assertRaisesRegex(AssertionError, "非空可执行文件"):
                run.case.test_download_142_kernel_and_verify_environment()
            run.environment.create_environment_with_kernel.assert_not_called()
            run.environment.clear_search.assert_not_called()

    def test_download_wait_failure_is_not_masked_and_does_not_create_environment(self):
        with self.configured_flow() as run:
            failure = TimeoutError("download did not finish")
            run.settings.wait_kernel_download_completed.side_effect = failure
            with self.assertRaises(TimeoutError) as raised:
                run.case.test_download_142_kernel_and_verify_environment()
            self.assertIs(raised.exception, failure)
            run.environment.create_environment_with_kernel.assert_not_called()
            run.environment.clear_search.assert_not_called()

    def test_failed_ui_deletion_confirmation_stops_before_download(self):
        with self.configured_flow() as run:
            run.settings.download_record_kernel_versions.return_value = ["142.1.1"]
            with self.assertRaisesRegex(AssertionError, "下载记录删除后仍有残留"):
                run.case.test_download_142_kernel_and_verify_environment()
            run.settings.download_latest_kernel.assert_not_called()
            run.environment.create_environment_with_kernel.assert_not_called()

    def assert_cache_residue_stops_flow(self, run, residue: Path, major: str = "142"):
        with mock.patch.object(flow.time, "monotonic", side_effect=count(0, 31)), mock.patch.object(
            flow.time, "sleep"
        ):
            with self.assertRaisesRegex(AssertionError, "本地缓存仍有残留") as raised:
                getattr(run.case, f"test_download_{major}_kernel_and_verify_environment")()
        self.assertIn(repr(str(residue)), str(raised.exception))
        self.assertTrue(residue.exists())
        run.settings.download_latest_kernel.assert_not_called()
        run.environment.create_environment_with_kernel.assert_not_called()

    def test_ui_record_removal_does_not_accept_a_remaining_local_directory(self):
        for major in ("142", "152"):
            with self.subTest(major=major), self.configured_flow(major) as run:
                run.settings.delete_downloaded_kernels.side_effect = lambda version: [run.previous.name]
                self.assert_cache_residue_stops_flow(run, run.previous, major)
                run.settings.download_record_kernel_versions.assert_called_once_with(major)

    def test_remaining_kernel_in_macos_sibling_cache_stops_download(self):
        with self.configured_flow() as run:
            residue = run.root.parent / "DICloak" / "browsers" / run.previous.name
            residue.mkdir(parents=True)
            # The direct cache can still contain another major and be chosen by the resolver.
            other = run.browsers / "152.1.2"
            other.mkdir()
            self.assert_cache_residue_stops_flow(run, residue)
            self.assertTrue(other.is_dir())

    def test_version_named_file_left_after_ui_deletion_stops_download(self):
        with self.configured_flow() as run:
            def leave_file(version):
                shutil.rmtree(run.previous)
                run.previous.write_bytes(b"leftover kernel cache entry")
                return [run.previous.name]

            run.settings.delete_downloaded_kernels.side_effect = leave_file
            self.assert_cache_residue_stops_flow(run, run.previous)
            self.assertTrue(run.previous.is_file())

    def test_waits_for_delayed_local_deletion_before_downloading(self):
        with self.configured_flow() as run:
            def request_deletion(version):
                run.events.append("delete_kernel")
                return [run.previous.name]

            def finish_deletion(interval):
                self.assertTrue(run.previous.is_dir())
                shutil.rmtree(run.previous)
                run.events.append("cache_deleted")

            run.settings.delete_downloaded_kernels.side_effect = request_deletion
            with mock.patch.object(flow.time, "monotonic", side_effect=count(0, 0.1)), mock.patch.object(
                flow.time, "sleep", side_effect=finish_deletion
            ) as sleep:
                run.case.test_download_142_kernel_and_verify_environment()
            sleep.assert_called_once_with(0.2)
            self.assertLess(run.events.index("cache_deleted"), run.events.index("download_kernel"))
            self.assertFalse(run.previous.exists())
            run.environment.create_environment_with_kernel.assert_called_once()

    def test_other_major_caches_are_preserved_and_do_not_block_target_deletion(self):
        for major, other_major in (("142", "152"), ("152", "142")):
            with self.subTest(major=major), self.configured_flow(major) as run:
                preserved = [
                    run.browsers / f"{other_major}.1.2" / "ginsbrowser",
                    run.root.parent / "DICloak" / "browsers" / f"{other_major}.1.3" / "ginsbrowser",
                ]
                for binary in preserved:
                    binary.parent.mkdir(parents=True)
                    binary.write_bytes(b"unrelated kernel")
                getattr(run.case, f"test_download_{major}_kernel_and_verify_environment")()
                self.assertFalse(run.previous.exists())
                self.assertTrue(all(binary.read_bytes() == b"unrelated kernel" for binary in preserved))
                run.settings.download_latest_kernel.assert_called_once_with(major)

    def test_refresh_deletes_all_cached_versions_before_the_download_flow_continues(self):
        for major, other_major in (("142", "152"), ("152", "142")):
            with self.subTest(major=major), self.configured_flow(major) as run:
                target_paths = [run.previous, run.browsers / f"{major}.1.9", run.browsers / f"{major}.1.11"]
                for path in target_paths[1:]:
                    path.mkdir()
                    (path / "ginsbrowser").write_bytes(b"older kernel")
                preserved = run.browsers / f"{other_major}.1.2"
                preserved.mkdir()
                (preserved / "ginsbrowser").write_bytes(b"unrelated kernel")
                damaged = run.browsers / f"{major}.0.7"
                damaged.mkdir()
                (damaged / "ginsbrowser").write_bytes(b"")
                installed = {path.name: path for path in [*target_paths, preserved]}
                records = [{"version": target_paths[0].name, "deletable": True}]
                deleted = []
                empty_snapshots = []
                settings = PersonalSettingsPage(cdp_driver=mock.MagicMock(), config={})
                for name in (
                    "open_from_avatar", "open_basic_settings", "environment_cache_dir",
                    "download_latest_kernel", "wait_kernel_download_completed",
                ):
                    setattr(settings, name, getattr(run.settings, name))
                settings.open_download_record_kernel_tab = mock.Mock()

                def read_records():
                    if not records and deleted:
                        empty_snapshots.append(deleted[-1])
                    return list(records)

                def refresh_records():
                    targets = [version for version in installed if version.split(".", 1)[0] == major]
                    # The APP exposes the next older version only after a refresh.
                    visible = targets[:1] + [preserved.name]
                    records[:] = [{"version": version, "deletable": True} for version in visible]

                def click_delete(script):
                    match = re.search(r"const expectedVersion = (.*?);", script)
                    self.assertIsNotNone(match)
                    version = json.loads(match.group(1))
                    self.assertEqual(version.split(".", 1)[0], major)
                    shutil.rmtree(installed.pop(version))
                    deleted.append(version)
                    records.clear()

                settings._download_record_kernel_states = mock.Mock(side_effect=read_records)
                settings.refresh_download_record_kernels = mock.Mock(side_effect=refresh_records)
                settings.cdp.click_element_by_script.side_effect = click_delete
                run.mocked["PersonalSettingsPage"].return_value = settings
                original_download = run.settings.download_latest_kernel.side_effect

                def download_after_all_deletions(version):
                    self.assertEqual(deleted, [path.name for path in target_paths])
                    self.assertTrue(all(not path.exists() for path in target_paths))
                    self.assertEqual(list(installed), [preserved.name])
                    self.assertEqual((preserved / "ginsbrowser").read_bytes(), b"unrelated kernel")
                    self.assertEqual((damaged / "ginsbrowser").read_bytes(), b"")
                    return original_download(version)

                run.settings.download_latest_kernel.side_effect = download_after_all_deletions
                with mock.patch.object(flow.time, "monotonic", side_effect=count(0, 0.1)), mock.patch.object(
                    flow.time, "sleep"
                ):
                    getattr(run.case, f"test_download_{major}_kernel_and_verify_environment")()
                self.assertEqual(deleted, [path.name for path in target_paths])
                self.assertEqual(empty_snapshots, deleted)
                self.assertGreaterEqual(settings.refresh_download_record_kernels.call_count, 4)
                self.assertEqual(settings.cdp.click_element_by_script.call_count, 3)
                self.assertEqual((preserved / "ginsbrowser").read_bytes(), b"unrelated kernel")
                self.assertEqual((damaged / "ginsbrowser").read_bytes(), b"")
                run.settings.download_latest_kernel.assert_called_once_with(major)
                run.environment.create_environment_with_kernel.assert_called_once()
                self.assertFalse(run.state["visible"])

    def test_unrecognized_damaged_same_major_cache_is_not_part_of_deletion_verification(self):
        for major in ("142", "152"):
            with self.subTest(major=major), self.configured_flow(major) as run:
                damaged = run.browsers / f"{major}.0.7"
                damaged.mkdir()
                (damaged / "ginsbrowser").write_bytes(b"")
                getattr(run.case, f"test_download_{major}_kernel_and_verify_environment")()
                self.assertFalse(run.previous.exists())
                self.assertEqual((damaged / "ginsbrowser").read_bytes(), b"")
                run.settings.download_latest_kernel.assert_called_once_with(major)
                run.environment.create_environment_with_kernel.assert_called_once()

    def test_unrecognized_higher_cache_cannot_replace_the_exact_downloaded_version(self):
        for major in ("142", "152"):
            with self.subTest(major=major), self.configured_flow(major) as run:
                damaged = run.browsers / f"{major}.9.9" / "core" / "ginsbrowser"
                damaged.parent.mkdir(parents=True)
                damaged.write_bytes(b"nonempty executable from an unrecognized cache")
                downloaded = run.root.parent / "DICloak" / "browsers" / run.latest.name
                binary = downloaded / "core" / "ginsbrowser"

                def download_to_macos_cache(version):
                    self.assertEqual(version, major)
                    self.assertFalse(run.previous.exists())
                    run.events.append("download_kernel")
                    binary.parent.mkdir(parents=True)
                    binary.write_bytes(b"new kernel")
                    return downloaded.name

                run.settings.download_latest_kernel.side_effect = download_to_macos_cache
                run.mocked["resolve_kernel_browsers_dir"].side_effect = kernel_cache.resolve_kernel_browsers_dir
                run.mocked["wait_for_kernel_executable_dir"].side_effect = kernel_cache.wait_for_kernel_executable_dir
                run.mocked["process_executable_path_by_pid"].return_value = str(binary)
                # A wrong root must fail promptly rather than wait the production timeout.
                with mock.patch.object(kernel_cache.time, "time", side_effect=count(0, 100)), mock.patch.object(
                    kernel_cache.time, "sleep"
                ):
                    getattr(run.case, f"test_download_{major}_kernel_and_verify_environment")()
                run.mocked["resolve_kernel_browsers_dir"].assert_called_once_with(
                    run.root, version=downloaded.name
                )
                run.mocked["wait_for_kernel_executable_dir"].assert_called_once_with(
                    downloaded.parent,
                    major,
                    executable_name="ginsbrowser",
                    timeout_seconds=300,
                    version=downloaded.name,
                )
                self.assertEqual(damaged.read_bytes(), b"nonempty executable from an unrecognized cache")
                self.assertEqual(binary.read_bytes(), b"new kernel")
                run.environment.create_environment_with_kernel.assert_called_once()
                self.assertFalse(run.state["visible"])

    def test_missing_ui_kernel_skips_local_deletion_check(self):
        with self.configured_flow(downloaded_before=False) as run:
            residue = run.browsers / "142.0.7"
            residue.mkdir(parents=True)
            with mock.patch.object(
                run.case, "_assert_kernel_directories_deleted", side_effect=AssertionError("不应执行删除校验")
            ) as check:
                run.case.test_download_142_kernel_and_verify_environment()
            check.assert_not_called()
            self.assertTrue(residue.is_dir())
            run.settings.download_record_kernel_versions.assert_not_called()
            run.environment.create_environment_with_kernel.assert_called_once()

    def test_wrong_running_major_still_closes_and_deletes_the_created_environment(self):
        with self.configured_flow("152") as run:
            run.mocked["kernel_version_from_cdp"].return_value = "142.0.1"
            with self.assertRaisesRegex(AssertionError, "实际启动内核版本不正确"):
                run.case.test_download_152_kernel_and_verify_environment()
            self.assertEqual(run.events[-2:], ["close_environment", "delete_environment"])
            self.assertFalse(run.state["visible"])
            self.assertEqual(run.environment.clear_search.call_count, 2)

    def test_same_major_from_a_different_installation_is_rejected(self):
        with self.configured_flow() as run:
            run.mocked["process_executable_path_by_pid"].return_value = str(run.latest.parent / "bundled" / "ginsbrowser")
            with self.assertRaisesRegex(AssertionError, "未使用本次下载的内核"):
                run.case.test_download_142_kernel_and_verify_environment()
            self.assertFalse(run.state["visible"])

    def test_partial_environment_creation_is_cleaned_up_without_losing_original_error(self):
        with self.configured_flow() as run:
            def create_then_fail(name, label):
                run.state["visible"] = True
                raise TimeoutError("create dialog did not close")

            run.environment.create_environment_with_kernel.side_effect = create_then_fail
            with self.assertRaisesRegex(TimeoutError, "create dialog did not close"):
                run.case.test_download_142_kernel_and_verify_environment()
            run.environment.delete_environment_from_current_list.assert_called_once()
            self.assertFalse(run.state["visible"])


if __name__ == "__main__":
    unittest.main()
