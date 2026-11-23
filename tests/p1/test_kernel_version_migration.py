from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from core.case_display import case_display_name
from core.config import REQUIRED_SECTIONS, load_config


class _EnvironmentPage:
    def __init__(self):
        self.names: list[str] = []
        self.open_names: set[str] = set()
        self.created_kernel = ""

    def open_list(self):
        pass

    def search_environment_without_assert(self, name):
        pass

    def clear_search(self):
        pass

    def clear_selected_environments(self):
        pass

    def environment_names_by_prefix_in_current_list(self, prefix):
        return [name for name in self.names if name.startswith(prefix)]

    def delete_environments_by_prefix_from_current_list(self, prefix):
        self.names = [name for name in self.names if not name.startswith(prefix)]

    def wait_no_environment_by_prefix_in_current_list(self, prefix):
        assert not self.environment_names_by_prefix_in_current_list(prefix)

    def create_environment_with_kernel(self, name, kernel):
        self.created_kernel = kernel
        self.names = [name]

    def batch_create_environments_with_kernel(self, prefix, count, kernel):
        self.created_kernel = kernel
        self.names = [f"{prefix}-{index}" for index in range(count)]

    def wait_environment_count_by_prefix_in_current_list(self, prefix, count):
        return self.environment_names_by_prefix_in_current_list(prefix)

    def wait_environment_visible_in_current_list(self, name):
        assert name in self.names

    def environment_visible_in_current_list(self, name):
        return name in self.names

    def environment_action_text(self, name):
        return "关闭" if name in self.open_names else "打开"

    def open_environment_and_capture_pid(self, name):
        self.open_names.add(name)
        return 31001

    def select_environments(self, names):
        self.selected = names

    def open_selected_environments_and_capture_pids(self, **kwargs):
        self.open_names.update(self.selected)
        return [31001 + index for index in range(len(self.selected))]

    def wait_environment_action_text(self, *args, **kwargs):
        pass

    def wait_environments_action_text(self, *args, **kwargs):
        pass

    def click_environment_action(self, name, action):
        self.open_names.discard(name)

    def click_batch_action(self, action):
        self.open_names.difference_update(self.selected)

    def confirm_secondary_dialog_if_present(self):
        pass

    def delete_environment_from_current_list(self, name):
        self.names.remove(name)


class KernelVersionMigrationTests(unittest.TestCase):
    def _run_case(self, *, batch: bool, actual_versions: list[str]):
        suffix = "test_05_batch_create_142_kernel_environments" if batch else "test_04_create_142_kernel_environment"
        module = importlib.import_module("tests.p0.environment_management." + suffix)
        class_name = "TestBatchCreate142KernelEnvironments" if batch else "TestCreate142KernelEnvironment"
        method = (
            "test_batch_create_open_verify_close_delete_142_kernel_environments"
            if batch else "test_create_open_verify_close_delete_142_kernel_environment"
        )
        case = getattr(module, class_name)(method)
        case.config = {"test_data": {"environment_batch_create_142_kernel": {"create_count": 2}}}
        case.cdp = object()
        page = _EnvironmentPage()
        runtime = SimpleNamespace(cdp_port=18888, command_line="")
        with (
            patch.object(module, "EnvironmentPage", return_value=page),
            patch.object(module, "wait_for_pid_running", return_value=True),
            patch.object(module, "wait_for_pid_stopped", return_value=True),
            patch.object(module, "resolve_kernel_runtime", return_value=runtime),
            patch.object(module, "kernel_version_from_cdp", side_effect=actual_versions) as read_version,
        ):
            try:
                getattr(case, method)()
            finally:
                self.assertEqual(page.created_kernel, "ChromeBrowser 142")
                self.assertFalse(page.open_names)
                self.assertFalse(page.names)
        return read_version.call_count, method

    def test_single_case_selects_and_checks_142(self):
        count, method = self._run_case(batch=False, actual_versions=["142.0.7444.0"])
        self.assertEqual(count, 1)
        self.assertEqual(case_display_name(method), "创建 142 内核环境并验证启动")

    def test_batch_case_checks_every_created_kernel(self):
        count, method = self._run_case(batch=True, actual_versions=["142.0.7444.0", "142.0.7444.0"])
        self.assertEqual(count, 2)
        self.assertEqual(case_display_name(method), "批量创建 142 内核环境并验证启动")

    def test_single_case_rejects_the_new_default_152_and_cleans_up(self):
        with self.assertRaisesRegex(AssertionError, "kernel version should start with 142"):
            self._run_case(batch=False, actual_versions=["152.0.1"])

    def test_batch_case_rejects_a_wrong_version_among_multiple_kernels(self):
        with self.assertRaisesRegex(AssertionError, "kernel version should start with 142"):
            self._run_case(batch=True, actual_versions=["142.0.7444.0", "152.0.1"])

    def _load(self, test_data, *, external_test_data=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = {section: {} for section in REQUIRED_SECTIONS}
            config["test_data"] = test_data
            config_path = root / "config.yaml"
            config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
            if external_test_data is not None:
                (root / "test_data.yaml").write_text(
                    yaml.safe_dump({"test_data": external_test_data}), encoding="utf-8"
                )
            return load_config(config_path, ignore_runtime_profiles=True)

    def test_legacy_batch_count_is_preserved_when_loading_existing_config(self):
        config = self._load({"environment_batch_create_134_kernel": {"create_count": 7}})
        self.assertEqual(config["test_data"]["environment_batch_create_142_kernel"]["create_count"], 7)

    def test_new_batch_config_takes_priority_over_legacy_key(self):
        config = self._load({
            "environment_batch_create_134_kernel": {"create_count": 7},
            "environment_batch_create_142_kernel": {"create_count": 2},
        })
        self.assertEqual(config["test_data"]["environment_batch_create_142_kernel"]["create_count"], 2)

    def test_legacy_external_test_data_count_keeps_its_precedence(self):
        config = self._load(
            {"environment_batch_create_134_kernel": {"create_count": 2}},
            external_test_data={"environment_batch_create_134_kernel": {"create_count": 5}},
        )
        self.assertEqual(config["test_data"]["environment_batch_create_142_kernel"]["create_count"], 5)


if __name__ == "__main__":
    unittest.main()
