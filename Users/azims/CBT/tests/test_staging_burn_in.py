"""
Unit tests for the Staging Burn-In & Soak Validation script.
"""

from unittest.mock import patch
import pytest
from deploy.staging_burn_in import run_burn_in_validation


def test_staging_burn_in_validation_pass():
    with patch("deploy.staging_burn_in.http_get") as mock_http:
        mock_http.side_effect = [
            (200, '{"status":"ok"}'),
            (200, 'ctb_node_uptime_seconds 123.45'),
            (200, '{"status":"OPERATIONAL"}'),
            (200, 'sky_shadow_open_positions 2'),
        ]

        report = run_burn_in_validation()
        assert report["all_passed"] is True
        assert report["passed_checks"] == 4
        assert "READY" in report["verdict"]


def test_staging_burn_in_validation_failure_handling():
    with patch("deploy.staging_burn_in.http_get") as mock_http:
        mock_http.side_effect = [
            (500, "Internal Server Error"),
            (200, 'ctb_node_uptime_seconds 123.45'),
            (200, '{"status":"OPERATIONAL"}'),
            (200, 'sky_shadow_open_positions 2'),
        ]

        report = run_burn_in_validation()
        assert report["all_passed"] is False
        assert report["passed_checks"] == 3
        assert "ACTION REQUIRED" in report["verdict"]
