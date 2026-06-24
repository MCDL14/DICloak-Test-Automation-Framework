from __future__ import annotations

import argparse
import io
import logging
import unittest

from core.run_metadata import (
    cli_run_start_fields,
    log_run_end,
    log_run_start,
    parse_run_metadata,
    run_scope_label,
)


class RunMetadataTests(unittest.TestCase):
    def test_cli_run_start_fields_detects_repeated_cases(self) -> None:
        args = argparse.Namespace(
            precheck=False,
            case=["tests.p0.a.TestA.test_one", "tests.p0.b.TestB.test_two"],
            module=None,
            business_module=None,
            level=None,
            attach_existing_app=True,
        )

        fields = cli_run_start_fields(args)

        self.assertEqual(fields["source"], "CLI")
        self.assertEqual(fields["scope"], "cases")
        self.assertEqual(fields["selected_count"], 2)
        self.assertTrue(fields["attach_existing_app"])

    def test_log_and_parse_run_metadata(self) -> None:
        stream = io.StringIO()
        logger = logging.getLogger("test_run_metadata")
        logger.handlers.clear()
        logger.propagate = False
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)

        log_run_start(logger, source="CLI", scope="module", value="member_management")
        log_run_end(logger, source="CLI", exit_code=0, success=True)

        metadata = parse_run_metadata(stream.getvalue())

        self.assertEqual(metadata["start"]["source"], "CLI")
        self.assertEqual(metadata["start"]["scope"], "module")
        self.assertEqual(metadata["start"]["value"], "member_management")
        self.assertEqual(metadata["end"]["exit_code"], 0)
        self.assertTrue(metadata["end"]["success"])
        self.assertEqual(run_scope_label(metadata["start"]), "module:member_management")


if __name__ == "__main__":
    unittest.main()
