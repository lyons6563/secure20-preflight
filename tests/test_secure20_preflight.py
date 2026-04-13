"""
Pytest-compatible tests for the SECURE 2.0 Preflight Checker.

Covers:
- Compensation annualization logic
- Potential HCE threshold detection
- Roth-only catch-up violation detection
"""

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from secure20.rules.roth_catchup import (
    annualize_compensation,
    check_potential_hce,
    check_roth_only_catchup_hce,
    is_hce,
)


# ---------------------------------------------------------------------------
# Shared config fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cfg():
    return {
        "hce_threshold": {"current_year": 2024, "compensation_limit": 150000},
        "catch_up": {"roth_only_risk_year": 2024},
        "annualization": {"method": "gross_or_ytd"},
    }


@pytest.fixture
def cfg_gross():
    return {
        "hce_threshold": {"current_year": 2024, "compensation_limit": 150000},
        "catch_up": {"roth_only_risk_year": 2024},
        "annualization": {"method": "gross"},
    }


@pytest.fixture
def cfg_ytd():
    return {
        "hce_threshold": {"current_year": 2024, "compensation_limit": 150000},
        "catch_up": {"roth_only_risk_year": 2024},
        "annualization": {"method": "ytd"},
    }


def _record(**kwargs):
    """Build a minimal payroll record with sensible defaults."""
    defaults = {
        "employee_id": "EMP000",
        "employee_name": "Test Employee",
        "gross_pay": Decimal("5000.00"),
        "ytd_gross_pay": Decimal("0"),
        "pay_period_start": date(2024, 1, 1),
        "pay_period_end": date(2024, 1, 14),
        "catch_up_contribution": Decimal("0"),
        "catch_up_type": None,
    }
    return {**defaults, **kwargs}


# ---------------------------------------------------------------------------
# Annualization
# ---------------------------------------------------------------------------

class TestAnnualization:
    def test_gross_biweekly(self, cfg_gross):
        record = _record(gross_pay=Decimal("5000.00"))
        result, _ = annualize_compensation(record, cfg_gross)
        expected = Decimal("5000.00") * Decimal("365") / Decimal("14")
        assert abs(float(result) - float(expected)) < 0.01
        assert result > Decimal("130000")

    def test_gross_monthly(self, cfg_gross):
        record = _record(
            gross_pay=Decimal("10000.00"),
            pay_period_start=date(2024, 1, 1),
            pay_period_end=date(2024, 1, 31),
        )
        result, _ = annualize_compensation(record, cfg_gross)
        expected = Decimal("10000.00") * Decimal("365") / Decimal("31")
        assert abs(float(result) - float(expected)) < 0.01

    def test_gross_single_day(self, cfg_gross):
        record = _record(
            gross_pay=Decimal("1000.00"),
            pay_period_start=date(2024, 1, 1),
            pay_period_end=date(2024, 1, 1),
        )
        result, _ = annualize_compensation(record, cfg_gross)
        assert result == Decimal("1000.00") * Decimal("365")

    def test_gross_or_ytd_prefers_ytd(self, cfg):
        """When YTD > 0 and gross_or_ytd method, should use YTD projection.

        The engine computes days_elapsed = (pay_period_end - year_start).days + 1.
        pay_period_end=Apr 9 → (Apr 9 - Jan 1).days=99, +1=100 days elapsed.
        """
        record = _record(
            gross_pay=Decimal("5000.00"),
            ytd_gross_pay=Decimal("60000.00"),
            pay_period_start=date(2024, 1, 1),
            pay_period_end=date(2024, 4, 9),    # 99 days from Jan 1 → days_elapsed=100
        )
        result, _ = annualize_compensation(record, cfg)
        expected_ytd = Decimal("60000.00") * Decimal("365") / Decimal("100")
        assert abs(float(result) - float(expected_ytd)) < 0.01
        gross_only = Decimal("5000.00") * Decimal("365") / Decimal("14")
        assert result > gross_only

    def test_gross_or_ytd_falls_back_to_gross(self, cfg):
        record = _record(gross_pay=Decimal("5000.00"), ytd_gross_pay=Decimal("0"))
        result, _ = annualize_compensation(record, cfg)
        expected = Decimal("5000.00") * Decimal("365") / Decimal("14")
        assert abs(float(result) - float(expected)) < 0.01

    def test_returns_method_name(self, cfg_gross):
        _, method = annualize_compensation(_record(), cfg_gross)
        assert isinstance(method, str)
        assert len(method) > 0


# ---------------------------------------------------------------------------
# is_hce
# ---------------------------------------------------------------------------

class TestIsHce:
    def test_above_threshold_is_hce(self, cfg_gross):
        record = _record(gross_pay=Decimal("10000.00"))   # ~$260k
        assert is_hce(record, cfg_gross) is True

    def test_below_threshold_not_hce(self, cfg_gross):
        record = _record(gross_pay=Decimal("4000.00"))    # ~$104k
        assert is_hce(record, cfg_gross) is False


# ---------------------------------------------------------------------------
# Potential HCE detection
# ---------------------------------------------------------------------------

class TestPotentialHce:
    def test_flags_employee_at_threshold(self, cfg):
        # $5800 * 365 / 14 = ~$151,250 — clearly over the $150k limit
        record = _record(gross_pay=Decimal("5800.00"))
        violations = check_potential_hce([record], cfg)
        assert len(violations) == 1
        assert violations[0]["violation_type"] == "POTENTIAL_HCE"
        assert violations[0]["projected_annual_compensation"] >= 150000.0

    def test_flags_employee_above_threshold(self, cfg):
        record = _record(gross_pay=Decimal("10000.00"))  # ~$260k
        violations = check_potential_hce([record], cfg)
        assert len(violations) == 1

    def test_no_flag_below_threshold(self, cfg):
        record = _record(gross_pay=Decimal("4000.00"))   # ~$104k
        assert check_potential_hce([record], cfg) == []

    def test_ytd_projection_above_threshold(self, cfg):
        record = _record(
            gross_pay=Decimal("5000.00"),
            ytd_gross_pay=Decimal("80000.00"),
            pay_period_start=date(2024, 1, 1),
            pay_period_end=date(2024, 6, 29),    # day ~180
        )
        violations = check_potential_hce([record], cfg)
        assert len(violations) == 1
        assert violations[0]["projected_annual_compensation"] > 150000.0

    def test_just_below_threshold_not_flagged(self, cfg):
        record = _record(gross_pay=Decimal("5750.00"))
        violations = check_potential_hce([record], cfg)
        result, _ = annualize_compensation(record, cfg)
        if result < Decimal("150000"):
            assert violations == []


# ---------------------------------------------------------------------------
# Roth-only catch-up violation detection
# ---------------------------------------------------------------------------

class TestRothCatchupViolation:
    def test_hce_roth_catchup_flagged(self, cfg):
        record = _record(
            employee_id="EMP001",
            gross_pay=Decimal("10000.00"),
            catch_up_contribution=Decimal("750.00"),
            catch_up_type="Roth",
        )
        violations = check_roth_only_catchup_hce([record], cfg)
        assert len(violations) == 1
        assert violations[0]["violation_type"] == "ROTH_ONLY_CATCHUP_HCE"
        assert violations[0]["employee_id"] == "EMP001"
        assert violations[0]["catch_up_amount"] == 750.0
        assert violations[0]["projected_annual_compensation"] > 150000.0

    def test_traditional_catchup_not_flagged(self, cfg):
        record = _record(
            gross_pay=Decimal("10000.00"),
            catch_up_contribution=Decimal("750.00"),
            catch_up_type="Traditional",
        )
        assert check_roth_only_catchup_hce([record], cfg) == []

    def test_non_hce_roth_not_flagged(self, cfg):
        record = _record(
            gross_pay=Decimal("4000.00"),
            catch_up_contribution=Decimal("500.00"),
            catch_up_type="Roth",
        )
        assert check_roth_only_catchup_hce([record], cfg) == []

    def test_no_catchup_not_flagged(self, cfg):
        record = _record(
            gross_pay=Decimal("10000.00"),
            catch_up_contribution=Decimal("0"),
            catch_up_type=None,
        )
        assert check_roth_only_catchup_hce([record], cfg) == []

    def test_before_risk_year_not_flagged(self):
        pre_risk_cfg = {
            "hce_threshold": {"current_year": 2023, "compensation_limit": 150000},
            "catch_up": {"roth_only_risk_year": 2024},
            "annualization": {"method": "gross_or_ytd"},
        }
        record = _record(
            employee_id="EMP005",
            gross_pay=Decimal("10000.00"),
            pay_period_start=date(2023, 1, 1),
            pay_period_end=date(2023, 1, 14),
            catch_up_contribution=Decimal("750.00"),
            catch_up_type="Roth",
        )
        assert check_roth_only_catchup_hce([record], pre_risk_cfg) == []

    def test_multiple_employees_only_hce_roth_flagged(self, cfg):
        records = [
            _record(employee_id="E1", gross_pay=Decimal("10000.00"),
                    catch_up_contribution=Decimal("750.00"), catch_up_type="Roth"),
            _record(employee_id="E2", gross_pay=Decimal("10000.00"),
                    catch_up_contribution=Decimal("750.00"), catch_up_type="Traditional"),
            _record(employee_id="E3", gross_pay=Decimal("4000.00"),
                    catch_up_contribution=Decimal("500.00"), catch_up_type="Roth"),
        ]
        violations = check_roth_only_catchup_hce(records, cfg)
        assert len(violations) == 1
        assert violations[0]["employee_id"] == "E1"
