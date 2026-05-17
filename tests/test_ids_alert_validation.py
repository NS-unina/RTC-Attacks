from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from experiments.pipeline.ids_dataset_pipeline import (
    AlertRecord,
    AttackEvent,
    load_attack_events_from_runner_summary,
    validate_alerts_against_events,
)


BASE_TIME = datetime(2026, 5, 16, 10, 0, 0, tzinfo=timezone.utc)


def _alert(offset_sec: float, sid: int) -> AlertRecord:
    return AlertRecord(
        timestamp=BASE_TIME + timedelta(seconds=offset_sec),
        src_ip="10.0.0.1",
        dst_ip="10.0.0.2",
        src_port=1000,
        dst_port=2000,
        protocol="tcp",
        sid=sid,
        msg=f"sid {sid}",
        attack_type="test",
    )


def _event(
    start_sec: float,
    end_sec: float,
    scenario_id: int,
    instance: str = "1",
    expected_sids: list[int] | None = None,
) -> AttackEvent:
    return AttackEvent(
        start_utc=BASE_TIME + timedelta(seconds=start_sec),
        end_utc=BASE_TIME + timedelta(seconds=end_sec),
        scenario_id=scenario_id,
        instance=instance,
        expected_sids=expected_sids,
    )


def _report(alerts: list[AlertRecord], events: list[AttackEvent]) -> dict:
    return validate_alerts_against_events(
        alerts=alerts,
        events=events,
        window_pre_sec=0.0,
        window_post_sec=0.0,
        timeline_bin_sec=1.0,
    )


class EventLevelAlertValidationTest(unittest.TestCase):
    def test_single_scenario_correct_sid_passes(self) -> None:
        report = _report([_alert(0.5, 2000001)], [_event(0.0, 2.0, 1)])

        self.assertTrue(report["validation_passed"])
        self.assertEqual(report["confusion_matrix"], {"TP": 1, "TN": 0, "FP": 0, "FN": 0})
        self.assertEqual(report["metrics"]["event_recall"], 1.0)

    def test_single_scenario_without_alert_is_fn(self) -> None:
        report = _report([], [_event(0.0, 0.9, 1)])

        self.assertFalse(report["validation_passed"])
        self.assertEqual(report["confusion_matrix"]["FN"], 1)

    def test_alert_without_attack_is_fp(self) -> None:
        report = _report([_alert(0.5, 2000001)], [])

        self.assertFalse(report["validation_passed"])
        self.assertEqual(report["confusion_matrix"]["FP"], 1)

    def test_overlapping_scenarios_with_both_sids_pass(self) -> None:
        report = _report(
            [_alert(0.4, 2000002), _alert(0.6, 2000008)],
            [_event(0.0, 0.9, 2), _event(0.0, 0.9, 8, expected_sids=[2000008])],
        )

        self.assertTrue(report["validation_passed"])
        self.assertEqual(report["confusion_matrix"]["TP"], 2)

    def test_overlapping_scenarios_with_one_sid_still_detects_both_windows(self) -> None:
        report = _report(
            [_alert(0.5, 2000002)],
            [_event(0.0, 0.9, 2), _event(0.0, 0.9, 8, expected_sids=[2000008])],
        )

        self.assertTrue(report["validation_passed"])
        self.assertEqual(report["confusion_matrix"]["TP"], 2)
        self.assertEqual(report["confusion_matrix"]["FN"], 0)

    def test_wrong_scenario_sid_is_fp_without_fn(self) -> None:
        report = _report([_alert(0.5, 2000002)], [_event(0.0, 0.9, 1)])

        self.assertFalse(report["validation_passed"])
        self.assertEqual(report["confusion_matrix"]["TP"], 1)
        self.assertEqual(report["confusion_matrix"]["FP"], 1)
        self.assertEqual(report["confusion_matrix"]["FN"], 0)
        self.assertEqual(report["confusion_by_sid"]["2000002"]["FP"], 1)

    def test_parallel_instances_with_same_sid_need_one_expected_sid(self) -> None:
        report = _report(
            [_alert(0.5, 2000001)],
            [_event(0.0, 0.9, 1, "a"), _event(0.0, 0.9, 1, "b")],
        )

        self.assertTrue(report["validation_passed"])
        self.assertEqual(report["confusion_matrix"]["TP"], 2)

    def test_runner_summary_prefers_ipc_attack_window(self) -> None:
        payload = {
            "results": [
                {
                    "scenario_id": 1,
                    "instance": "1",
                    "success": True,
                    "start_utc": "2026-05-16T09:59:00Z",
                    "end_utc": "2026-05-16T10:02:00Z",
                }
            ],
            "ipc_events": [
                {
                    "state": "lab_ready",
                    "scenario": 1,
                    "instance": "1",
                    "ts_utc": "2026-05-16T09:59:10Z",
                },
                {
                    "state": "attack_start",
                    "scenario": 1,
                    "instance": "1",
                    "attack": "sip_spoofing",
                    "ts_utc": "2026-05-16T10:00:00Z",
                },
                {
                    "state": "attack_end",
                    "scenario": 1,
                    "instance": "1",
                    "attack": "sip_spoofing",
                    "ts_utc": "2026-05-16T10:00:02Z",
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            summary = Path(tmp_dir) / "summary.json"
            summary.write_text(json.dumps(payload), encoding="utf-8")
            events = load_attack_events_from_runner_summary(summary, only_success=True)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].start_utc, BASE_TIME)
        self.assertEqual(events[0].end_utc, BASE_TIME + timedelta(seconds=2))


if __name__ == "__main__":
    unittest.main()
