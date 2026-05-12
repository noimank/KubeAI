import pytest

from app.integrations.volcano.client import extract_vcjob_phase


class TestExtractVcjobPhase:
    def test_state_phase_completed(self):
        vcjob = {"status": {"state": {"phase": "Completed"}, "runningDuration": "5s"}}
        assert extract_vcjob_phase(vcjob) == "succeeded"

    def test_state_phase_running(self):
        vcjob = {"status": {"state": {"phase": "Running"}}}
        assert extract_vcjob_phase(vcjob) == "running"

    def test_state_phase_pending(self):
        vcjob = {"status": {"state": {"phase": "Pending"}}}
        assert extract_vcjob_phase(vcjob) == "pending"

    def test_state_phase_inqueue(self):
        vcjob = {"status": {"state": {"phase": "Inqueue"}}}
        assert extract_vcjob_phase(vcjob) == "queued"

    def test_state_phase_failed(self):
        vcjob = {"status": {"state": {"phase": "Failed"}}}
        assert extract_vcjob_phase(vcjob) == "failed"

    def test_state_phase_terminated(self):
        vcjob = {"status": {"state": {"phase": "Terminated"}}}
        assert extract_vcjob_phase(vcjob) == "stopped"

    def test_no_state_falls_back_to_status_phase(self):
        vcjob = {"status": {"phase": "Running"}}
        assert extract_vcjob_phase(vcjob) == "running"

    def test_no_status_defaults_to_pending(self):
        vcjob = {}
        assert extract_vcjob_phase(vcjob) == "pending"

    def test_empty_state_defaults_to_pending(self):
        vcjob = {"status": {"state": {}}}
        assert extract_vcjob_phase(vcjob) == "pending"

    def test_unknown_phase_falls_back_to_pending(self):
        vcjob = {"status": {"state": {"phase": "SomeNewPhase"}}}
        assert extract_vcjob_phase(vcjob) == "pending"

    @pytest.mark.parametrize(
        "phase,expected",
        [
            ("Completed", "succeeded"),
            ("Running", "running"),
            ("Pending", "pending"),
            ("Inqueue", "queued"),
            ("Failed", "failed"),
            ("Terminated", "stopped"),
        ],
    )
    def test_all_phases_via_state(self, phase, expected):
        vcjob = {"status": {"state": {"phase": phase}}}
        assert extract_vcjob_phase(vcjob) == expected
