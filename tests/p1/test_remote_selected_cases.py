from __future__ import annotations

import logging
import unittest

from core.remote_runner import RemoteHost, RemoteRunRequest, build_remote_command
from core.runner import AutomationRunner
from run import parse_args


class RemoteSelectedCasesTests(unittest.TestCase):
    def test_parse_args_accepts_repeated_case(self) -> None:
        args = parse_args(["--case", "tests.p0.a.TestA.test_one", "--case", "tests.p0.b.TestB.test_two"])

        self.assertEqual(args.case, ["tests.p0.a.TestA.test_one", "tests.p0.b.TestB.test_two"])

    def test_runner_filters_multiple_cases(self) -> None:
        class SampleCase(unittest.TestCase):
            def test_one(self) -> None:
                pass

            def test_two(self) -> None:
                pass

            def test_three(self) -> None:
                pass

        suite = unittest.defaultTestLoader.loadTestsFromTestCase(SampleCase)
        runner = AutomationRunner(
            config={"run": {}, "feishu": {"enabled": False}},
            logger=logging.getLogger("test_remote_selected_cases"),
        )

        filtered = runner._filter_suite_by_cases(
            suite,
            ("SampleCase.test_one", "SampleCase.test_three"),
        )

        self.assertEqual(filtered.countTestCases(), 2)
        self.assertEqual(
            [test.id().rsplit(".", 1)[-1] for test in runner._iter_tests(filtered)],
            ["test_one", "test_three"],
        )

    def test_remote_command_accepts_multiple_cases(self) -> None:
        host = RemoteHost(
            name="macos-arm64",
            host="127.0.0.1",
            username="tester",
            project_dir="/tmp/dicloak",
            config="config/config.macos.yaml",
            venv_activate=".venv/bin/activate",
        )
        request = RemoteRunRequest(
            scope="cases",
            values=("tests.p0.a.TestA.test_one", "tests.p0.b.TestB.test_two"),
            attach_existing_app=True,
        )

        command = build_remote_command(host, request)

        self.assertIn("--case tests.p0.a.TestA.test_one", command)
        self.assertIn("--case tests.p0.b.TestB.test_two", command)
        self.assertIn("--attach-existing-app", command)


if __name__ == "__main__":
    unittest.main()
