from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping

from core.global_settings_baseline import (
    ORG_CONFIG_COMPARE_BLOCKS,
    ORG_CONFIG_EXPECTED_BLOCKS,
    ORG_CONFIG_READ_ONLY_BLOCKS,
    load_org_config_baseline,
)
from core.org_config_api import OrgConfigApiClient
from core.org_config_semantics import (
    format_org_config_diffs,
    merge_masked_value,
    semantic_org_config_diff,
)


BITMASK_TYPE_BLOCKS = frozenset({"browser_config", "data_sync_config"})


class GlobalSettingsRecoverySession:
    def __init__(
        self,
        cdp_driver,
        *,
        affected_blocks: Iterable[str],
        bitmask_blocks: Iterable[str] = (),
        api_client: OrgConfigApiClient | None = None,
        baseline: Mapping[str, object] | None = None,
    ) -> None:
        self.cdp = cdp_driver
        self.logger = getattr(cdp_driver, "logger", None)
        self.client = api_client or OrgConfigApiClient(cdp_driver)
        self.baseline = copy.deepcopy(dict(baseline or load_org_config_baseline()))
        self.affected_blocks = frozenset(affected_blocks)
        self.bitmask_blocks = frozenset(bitmask_blocks)
        invalid = sorted(self.affected_blocks - set(ORG_CONFIG_COMPARE_BLOCKS))
        if invalid:
            raise ValueError(f"unsupported global settings recovery blocks: {invalid}")
        invalid_masks = sorted(self.bitmask_blocks - BITMASK_TYPE_BLOCKS)
        if invalid_masks:
            raise ValueError(f"unsupported global settings bitmask blocks: {invalid_masks}")

        self.write_attempted = False
        self.changed_blocks: set[str] = set()
        self.changed_type_masks: dict[str, int] = {}

    def ensure_baseline_before_case(self) -> None:
        actual = self.client.get_org_config()
        diffs = semantic_org_config_diff(self.baseline, actual)
        if not diffs:
            self._log("info", "Global settings preflight already matches API baseline")
            return

        self._log(
            "warning",
            "Global settings preflight mismatch; restoring complete baseline: %s",
            format_org_config_diffs(diffs),
        )
        self.client.post_org_config(self.baseline)
        restored = self.client.get_org_config()
        remaining = semantic_org_config_diff(self.baseline, restored)
        if remaining:
            self._log(
                "warning",
                "Global settings preflight mismatch remains after restore; continuing: %s",
                format_org_config_diffs(remaining),
            )

    def mark_write_attempted(self) -> None:
        self.write_attempted = True

    def record_successful_post(self, payload: Mapping[str, object]) -> None:
        self.write_attempted = True
        for block in self.affected_blocks:
            expected_block = self.baseline.get(block)
            submitted_block = payload.get(block)
            if not isinstance(expected_block, Mapping) or not isinstance(submitted_block, Mapping):
                continue
            if block in self.bitmask_blocks:
                baseline_type = expected_block.get("type")
                submitted_type = submitted_block.get("type")
                if isinstance(baseline_type, int) and isinstance(submitted_type, int):
                    changed_mask = baseline_type ^ submitted_type
                    if changed_mask:
                        self.changed_type_masks[block] = (
                            self.changed_type_masks.get(block, 0) | changed_mask
                        )
                non_type_expected = {key: value for key, value in expected_block.items() if key != "type"}
                non_type_submitted = {
                    key: value for key, value in submitted_block.items() if key != "type"
                }
                if non_type_expected != non_type_submitted:
                    self.changed_blocks.add(block)
                continue
            if semantic_org_config_diff(
                self.baseline,
                payload,
                blocks=(block,),
            ):
                self.changed_blocks.add(block)

    def restore_if_needed(self) -> None:
        if not self.write_attempted:
            return

        actual = self.client.get_org_config()
        blocks, bit_masks = self._effective_scope(actual)
        if not blocks:
            return
        diffs = semantic_org_config_diff(
            self.baseline,
            actual,
            blocks=blocks,
            bit_masks=bit_masks,
        )
        if not diffs:
            self._log("info", "Global settings affected scope already restored; skipping POST")
            return

        payload = build_complete_restore_payload(
            current=actual,
            baseline=self.baseline,
            restore_blocks=blocks,
            bit_masks=bit_masks,
        )
        self.client.post_org_config(payload)
        restored = self.client.get_org_config()
        remaining = semantic_org_config_diff(
            self.baseline,
            restored,
            blocks=blocks,
            bit_masks=bit_masks,
        )
        if remaining:
            raise AssertionError(
                "global settings affected scope restore mismatch: "
                f"{format_org_config_diffs(remaining)}"
            )

    def _effective_scope(
        self,
        actual: Mapping[str, object],
    ) -> tuple[tuple[str, ...], dict[str, int]]:
        blocks = set(self.changed_blocks)
        masks = dict(self.changed_type_masks)
        for block in self.affected_blocks:
            if block not in self.bitmask_blocks:
                if block in self.changed_blocks:
                    blocks.add(block)
                    continue
                if semantic_org_config_diff(
                    self.baseline,
                    actual,
                    blocks=(block,),
                ):
                    blocks.add(block)
                continue
            if masks.get(block):
                blocks.add(block)
                continue
            baseline_block = self.baseline.get(block)
            actual_block = actual.get(block)
            if isinstance(baseline_block, Mapping) and isinstance(actual_block, Mapping):
                baseline_type = baseline_block.get("type")
                actual_type = actual_block.get("type")
                if isinstance(baseline_type, int) and isinstance(actual_type, int):
                    inferred_mask = baseline_type ^ actual_type
                    if inferred_mask:
                        masks[block] = inferred_mask
                        blocks.add(block)
        return tuple(block for block in ORG_CONFIG_COMPARE_BLOCKS if block in blocks), masks

    def _log(self, level: str, message: str, *args: object) -> None:
        if self.logger is not None:
            getattr(self.logger, level)(message, *args)


def build_complete_restore_payload(
    *,
    current: Mapping[str, object],
    baseline: Mapping[str, object],
    restore_blocks: Iterable[str],
    bit_masks: Mapping[str, int] | None = None,
) -> dict[str, object]:
    payload = copy.deepcopy(dict(baseline))
    for block in ORG_CONFIG_EXPECTED_BLOCKS:
        current_block = current.get(block)
        if isinstance(payload.get(block), dict) and isinstance(current_block, Mapping):
            payload[block].update(copy.deepcopy(dict(current_block)))
        elif block in current:
            payload[block] = copy.deepcopy(current_block)

    masks = dict(bit_masks or {})
    for block in restore_blocks:
        baseline_block = baseline.get(block)
        current_block = current.get(block)
        if block in masks and isinstance(baseline_block, Mapping) and isinstance(current_block, Mapping):
            mask = masks[block]
            baseline_type = baseline_block.get("type")
            current_type = current_block.get("type")
            if isinstance(baseline_type, int) and isinstance(current_type, int):
                target_block = payload.setdefault(block, {})
                if isinstance(target_block, dict):
                    target_block["type"] = merge_masked_value(current_type, baseline_type, mask)
            continue
        payload[block] = copy.deepcopy(baseline_block)

    for read_only in ORG_CONFIG_READ_ONLY_BLOCKS:
        payload.pop(read_only, None)
    return payload
