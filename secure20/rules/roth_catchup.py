"""
Roth Catch-up Rule for SECURE 2.0 Preflight Checker

This rule checks for:
1. HCEs subject to Roth-only catch-up requirement (RED findings)
2. Potential HCEs based on projected compensation (YELLOW findings)
"""

from decimal import Decimal
from datetime import date
from typing import Dict, List


def annualize_compensation(record: Dict, config: Dict) -> Decimal:
    """
    Calculate projected annual compensation for an employee.
    
    Args:
        record: Payroll record dictionary
        config: Configuration dictionary
        
    Returns:
        Projected annual compensation amount
    """
    method = config['annualization']['method']
    current_year = config['hce_threshold']['current_year']
    
    # Calculate days elapsed in year for YTD projection
    year_start = date(current_year, 1, 1)
    pay_period_end = record['pay_period_end']
    days_elapsed = (pay_period_end - year_start).days + 1  # +1 to include end date
    if days_elapsed <= 0:
        days_elapsed = 1  # Prevent division by zero
    
    # Method: ytd - always use YTD projection if available
    if method == 'ytd':
        if record['ytd_gross_pay'] > 0:
            return record['ytd_gross_pay'] * Decimal('365') / Decimal(str(days_elapsed))
        else:
            # Fallback to gross if YTD is zero/not available
            return _annualize_from_gross(record)
    
    # Method: gross_or_ytd - prefer YTD if available, otherwise use gross
    if method == 'gross_or_ytd':
        if record['ytd_gross_pay'] > 0:
            return record['ytd_gross_pay'] * Decimal('365') / Decimal(str(days_elapsed))
        else:
            return _annualize_from_gross(record)
    
    # Method: gross - always annualize from gross pay
    if method == 'gross':
        return _annualize_from_gross(record)
    
    # Should not reach here, but default to gross_or_ytd behavior
    return _annualize_from_gross(record)


def _annualize_from_gross(record: Dict) -> Decimal:
    """Annualize compensation from gross pay based on pay period frequency."""
    pay_period_start = record['pay_period_start']
    pay_period_end = record['pay_period_end']
    gross_pay = record['gross_pay']
    
    # Calculate pay period length in days
    pay_period_days = (pay_period_end - pay_period_start).days + 1  # +1 to include both dates
    if pay_period_days <= 0:
        pay_period_days = 1  # Prevent division by zero
    
    # Annualize: gross_pay * (365 / pay_period_days)
    return gross_pay * Decimal('365') / Decimal(str(pay_period_days))


def is_hce(record: Dict, config: Dict) -> bool:
    """
    Determine if an employee is a Highly Compensated Employee (HCE).
    
    Args:
        record: Payroll record dictionary
        config: Configuration dictionary
        
    Returns:
        True if employee is an HCE, False otherwise
    """
    projected_compensation = annualize_compensation(record, config)
    threshold = Decimal(str(config['hce_threshold']['compensation_limit']))
    return projected_compensation >= threshold


def check_roth_only_catchup_hce(payroll_data: List[Dict], config: Dict) -> List[Dict]:
    """
    Check 1: Identify HCEs subject to Roth-only catch-up requirement.
    
    Rule: For the year specified in catch_up.roth_only_risk_year and beyond,
    HCEs must make catch-up contributions as Roth-only (enforcement requirement).
    
    Args:
        payroll_data: List of payroll records
        config: Configuration dictionary
        
    Returns:
        List of violation dictionaries for exception CSV
    """
    violations = []
    current_year = config['hce_threshold']['current_year']
    roth_only_risk_year = config['catch_up']['roth_only_risk_year']
    
    # Only check if current year is >= roth_only_risk_year
    if current_year < roth_only_risk_year:
        return violations
    
    for record in payroll_data:
        # Filter employees with Roth catch-up contributions
        if (record.get('catch_up_contribution', Decimal('0')) > 0 and 
            record.get('catch_up_type') == 'Roth'):
            
            # Determine if employee is an HCE
            if is_hce(record, config):
                projected_comp = annualize_compensation(record, config)
                
                violation = {
                    'employee_id': record['employee_id'],
                    'employee_name': record['employee_name'],
                    'violation_type': 'ROTH_ONLY_CATCHUP_HCE',
                    'violation_description': (
                        f"Catch-up contributions must be Roth for this projected HCE under SECURE 2.0 (Roth-only requirement). "
                        f"Review payroll enforcement. Projected annual compensation: ${projected_comp:,.2f}"
                    ),
                    'projected_annual_compensation': float(projected_comp),
                    'catch_up_amount': float(record['catch_up_contribution']),
                    'catch_up_type': record['catch_up_type'],
                    'pay_period_start': record['pay_period_start'].strftime('%Y-%m-%d'),
                    'pay_period_end': record['pay_period_end'].strftime('%Y-%m-%d'),
                }
                violations.append(violation)
    
    return violations


def check_potential_hce(payroll_data: List[Dict], config: Dict) -> List[Dict]:
    """
    Check 2: Identify potential HCEs based on projected annual compensation.
    
    Rule: Identify employees who may become HCEs based on annualized compensation.
    
    Args:
        payroll_data: List of payroll records
        config: Configuration dictionary
        
    Returns:
        List of potential HCE records for exception CSV (informational)
    """
    potential_hces = []
    threshold = Decimal(str(config['hce_threshold']['compensation_limit']))
    
    for record in payroll_data:
        # Calculate projected annual compensation
        projected_comp = annualize_compensation(record, config)
        
        # Flag if projected compensation >= threshold
        if projected_comp >= threshold:
            potential_hce = {
                'employee_id': record['employee_id'],
                'employee_name': record['employee_name'],
                'violation_type': 'POTENTIAL_HCE',
                'violation_description': (
                    f"Potential HCE based on projected annual compensation: ${projected_comp:,.2f}"
                ),
                'projected_annual_compensation': float(projected_comp),
                'catch_up_amount': float(record.get('catch_up_contribution', Decimal('0'))),
                'catch_up_type': record.get('catch_up_type') or '',
                'pay_period_start': record['pay_period_start'].strftime('%Y-%m-%d'),
                'pay_period_end': record['pay_period_end'].strftime('%Y-%m-%d'),
            }
            potential_hces.append(potential_hce)
    
    return potential_hces

