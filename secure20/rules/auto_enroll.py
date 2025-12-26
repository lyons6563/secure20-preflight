"""
Auto-Enrollment and Escalation Rule for SECURE 2.0 Preflight Checker

This rule checks for:
1. Auto-enrollment misses (RED findings)
2. Auto-enrolled employees below default rate (YELLOW findings)
3. Possible escalation misses (YELLOW findings)
"""

from decimal import Decimal
from datetime import date, timedelta
from typing import Dict, List


def check_auto_enroll_required_columns(payroll_data: List[Dict]) -> bool:
    """
    Check if payroll data contains required columns for auto-enroll checks.
    
    Args:
        payroll_data: List of payroll records
        
    Returns:
        True if required columns are present, False otherwise
    """
    if not payroll_data:
        return False
    
    # Check first record for required columns
    first_record = payroll_data[0]
    required = ['hire_date', 'deferral_rate', 'deferral_start_date']
    
    # Check if any record has these keys (they might be optional in CSV)
    for record in payroll_data[:5]:  # Check first few records
        if all(key in record for key in required):
            return True
    
    return False


def check_auto_enroll_miss(payroll_data: List[Dict], config: Dict) -> List[Dict]:
    """
    Check for auto-enrollment misses (RED findings).
    
    Rule: If auto-enroll is enabled and employee should have been auto-enrolled
    but has no deferral_start_date or deferral_rate is 0.
    
    Args:
        payroll_data: List of payroll records
        config: Configuration dictionary
        
    Returns:
        List of violation dictionaries for exception CSV
    """
    findings = []
    
    # Check if rule is enabled
    if not config.get('auto_enroll_enabled', False):
        return findings
    
    # Check if required columns exist
    if not check_auto_enroll_required_columns(payroll_data):
        return findings
    
    wait_days = config.get('auto_enroll_wait_days', 0)
    current_year = config.get('hce_threshold', {}).get('current_year', 2024)
    
    for record in payroll_data:
        # Check if employee has hire_date
        hire_date_str = record.get('hire_date', '').strip()
        if not hire_date_str:
            continue
        
        try:
            # Parse hire_date (assuming YYYY-MM-DD format)
            hire_date = date.fromisoformat(hire_date_str)
        except (ValueError, TypeError):
            continue
        
        # Check if pay_period_end is >= hire_date + wait_days
        pay_period_end = record['pay_period_end']
        enrollment_date = hire_date + timedelta(days=wait_days)
        
        if pay_period_end < enrollment_date:
            continue  # Not yet eligible for auto-enrollment
        
        # Check deferral status
        deferral_start_date_str = record.get('deferral_start_date', '').strip()
        deferral_rate_str = record.get('deferral_rate', '').strip()
        
        deferral_rate = Decimal('0')
        if deferral_rate_str:
            try:
                deferral_rate = Decimal(deferral_rate_str)
            except (ValueError, TypeError):
                pass
        
        # Check if auto-enrollment should have occurred but didn't
        if not deferral_start_date_str or deferral_rate == 0:
            finding = {
                'employee_id': record['employee_id'],
                'employee_name': record['employee_name'],
                'violation_type': 'AUTO_ENROLL_MISS',
                'violation_description': (
                    f"Auto-enrollment miss: Employee hired {hire_date_str}, eligible from {enrollment_date.strftime('%Y-%m-%d')}, "
                    f"but no deferral start date or deferral rate is 0"
                ),
                'projected_annual_compensation': 0.0,
                'catch_up_amount': 0.0,
                'catch_up_type': '',
                'pay_period_start': record['pay_period_start'].strftime('%Y-%m-%d'),
                'pay_period_end': record['pay_period_end'].strftime('%Y-%m-%d'),
            }
            findings.append(finding)
    
    return findings


def check_auto_enroll_below_default(payroll_data: List[Dict], config: Dict) -> List[Dict]:
    """
    Check for auto-enrolled employees below default rate (YELLOW findings).
    
    Rule: If employee is auto-enrolled but deferral_rate is below default.
    
    Args:
        payroll_data: List of payroll records
        config: Configuration dictionary
        
    Returns:
        List of violation dictionaries for exception CSV
    """
    findings = []
    
    # Check if required columns exist
    if not check_auto_enroll_required_columns(payroll_data):
        return findings
    
    default_rate = Decimal(str(config.get('auto_enroll_default_rate', 0.03)))
    
    for record in payroll_data:
        deferral_start_date_str = record.get('deferral_start_date', '').strip()
        if not deferral_start_date_str:
            continue  # Not auto-enrolled
        
        deferral_rate_str = record.get('deferral_rate', '').strip()
        if not deferral_rate_str:
            continue
        
        try:
            deferral_rate = Decimal(deferral_rate_str)
        except (ValueError, TypeError):
            continue
        
        # Check if rate is below default
        if deferral_rate < default_rate:
            finding = {
                'employee_id': record['employee_id'],
                'employee_name': record['employee_name'],
                'violation_type': 'AUTO_ENROLL_BELOW_DEFAULT',
                'violation_description': (
                    f"Auto-enrolled employee below default rate: deferral_rate={deferral_rate:.1%}, "
                    f"default={default_rate:.1%}"
                ),
                'projected_annual_compensation': 0.0,
                'catch_up_amount': 0.0,
                'catch_up_type': '',
                'pay_period_start': record['pay_period_start'].strftime('%Y-%m-%d'),
                'pay_period_end': record['pay_period_end'].strftime('%Y-%m-%d'),
            }
            findings.append(finding)
    
    return findings


def check_escalation_miss(payroll_data: List[Dict], config: Dict) -> List[Dict]:
    """
    Check for possible escalation misses (YELLOW findings).
    
    Rule: If escalation is enabled and employee should have escalated
    but deferral_rate is still below default rate.
    
    Args:
        payroll_data: List of payroll records
        config: Configuration dictionary
        
    Returns:
        List of violation dictionaries for exception CSV
    """
    findings = []
    
    # Check if rule is enabled
    if not config.get('escalation_enabled', False):
        return findings
    
    # Check if required columns exist
    if not check_auto_enroll_required_columns(payroll_data):
        return findings
    
    escalation_effective_month = config.get('escalation_effective_month', 1)
    default_rate = Decimal(str(config.get('auto_enroll_default_rate', 0.03)))
    
    for record in payroll_data:
        deferral_start_date_str = record.get('deferral_start_date', '').strip()
        if not deferral_start_date_str:
            continue  # Not enrolled, skip escalation check
        
        pay_period_end = record['pay_period_end']
        
        # Check if pay_period_end month is >= escalation_effective_month (same year)
        if pay_period_end.month < escalation_effective_month:
            continue  # Not yet in escalation period
        
        deferral_rate_str = record.get('deferral_rate', '').strip()
        if not deferral_rate_str:
            continue
        
        try:
            deferral_rate = Decimal(deferral_rate_str)
        except (ValueError, TypeError):
            continue
        
        # Check if rate is still below default after escalation should have occurred
        if deferral_rate < default_rate:
            finding = {
                'employee_id': record['employee_id'],
                'employee_name': record['employee_name'],
                'violation_type': 'ESCALATION_POSSIBLE_MISS',
                'violation_description': (
                    f"Possible escalation miss detected: deferral_rate={deferral_rate:.1%} is below default={default_rate:.1%} "
                    f"after escalation effective month ({escalation_effective_month}). This may indicate an escalation issue; "
                    f"please verify plan schedule and employee election history to confirm."
                ),
                'projected_annual_compensation': 0.0,
                'catch_up_amount': 0.0,
                'catch_up_type': '',
                'pay_period_start': record['pay_period_start'].strftime('%Y-%m-%d'),
                'pay_period_end': record['pay_period_end'].strftime('%Y-%m-%d'),
            }
            findings.append(finding)
    
    return findings

