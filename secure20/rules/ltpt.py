"""
Long-Term Part-Time (LTPT) Eligibility Rule for SECURE 2.0 Preflight Checker

This rule checks for employees who may be eligible for LTPT status based on
hours worked in consecutive years.
"""

from decimal import Decimal
from typing import Dict, List, Optional


def load_hours_history(hours_data: List[Dict]) -> Dict[str, Dict[int, Decimal]]:
    """
    Build a per-employee year->hours map from hours history data.
    
    Args:
        hours_data: List of dictionaries with 'employee_id', 'year', 'hours' keys
        
    Returns:
        Dictionary mapping employee_id to a dictionary of year->hours
    """
    employee_hours = {}
    
    for record in hours_data:
        employee_id = str(record.get('employee_id', '')).strip()
        if not employee_id:
            continue
            
        try:
            year = int(record.get('year', 0))
            hours = Decimal(str(record.get('hours', 0)))
        except (ValueError, TypeError):
            continue
        
        if employee_id not in employee_hours:
            employee_hours[employee_id] = {}
        
        employee_hours[employee_id][year] = hours
    
    return employee_hours


def check_ltpt_eligibility(
    payroll_data: List[Dict],
    hours_data: Optional[List[Dict]],
    config: Dict
) -> List[Dict]:
    """
    Check for LTPT eligibility based on hours history.
    
    Rule: Employee must have worked >= threshold hours for N consecutive years
    ending at ltpt_latest_year.
    
    Args:
        payroll_data: List of payroll records
        hours_data: Optional list of hours history records
        config: Configuration dictionary
        
    Returns:
        List of finding dictionaries for exception CSV
    """
    findings = []
    
    # Check if rule is enabled
    if not config.get('ltpt_enabled', False):
        return findings
    
    # Check if hours data is provided
    if not hours_data:
        return findings
    
    # Load hours history
    employee_hours = load_hours_history(hours_data)
    
    # Get config parameters
    threshold = Decimal(str(config.get('ltpt_hours_threshold', 500)))
    consecutive_years = config.get('ltpt_consecutive_years_required', 3)
    latest_year = config.get('ltpt_latest_year', 2024)
    requires_deferral_absent = config.get('ltpt_requires_deferral_absent', False)
    
    # Validate consecutive_years
    if consecutive_years not in [2, 3]:
        return findings  # Invalid config, skip rule
    
    # Check each employee in payroll data
    for record in payroll_data:
        employee_id = record['employee_id']
        
        # Check if employee has hours history
        if employee_id not in employee_hours:
            continue
        
        hours_map = employee_hours[employee_id]
        
        # Check for consecutive years ending at latest_year
        qualifying_years = []
        for year_offset in range(consecutive_years - 1, -1, -1):
            year = latest_year - year_offset
            if year in hours_map and hours_map[year] >= threshold:
                qualifying_years.append((year, float(hours_map[year])))
            else:
                break  # Not consecutive, stop checking
        
        # If we found the required number of consecutive years
        if len(qualifying_years) == consecutive_years:
            # Optional: Check if deferral is absent (if required)
            if requires_deferral_absent:
                deferral_start_date = record.get('deferral_start_date', '').strip()
                deferral_rate_str = record.get('deferral_rate', '').strip()
                deferral_rate = Decimal('0')
                if deferral_rate_str:
                    try:
                        deferral_rate = Decimal(deferral_rate_str)
                    except (ValueError, TypeError):
                        pass
                
                # Skip if employee already has deferral
                if deferral_start_date or deferral_rate > 0:
                    continue
            
            # Build description with qualifying years and hours
            years_desc = ', '.join([f"{year} ({hours:.0f} hrs)" for year, hours in qualifying_years])
            
            finding = {
                'employee_id': employee_id,
                'employee_name': record['employee_name'],
                'violation_type': 'LTPT_POSSIBLE_ELIGIBLE',
                'violation_description': (
                    f"Possible LTPT eligibility: Employee worked >= {threshold:.0f} hours in "
                    f"{consecutive_years} consecutive years ({years_desc}). "
                    f"Verify eligibility and enrollment status."
                ),
                'projected_annual_compensation': 0.0,
                'catch_up_amount': 0.0,
                'catch_up_type': '',
                'pay_period_start': record['pay_period_start'].strftime('%Y-%m-%d'),
                'pay_period_end': record['pay_period_end'].strftime('%Y-%m-%d'),
            }
            findings.append(finding)
    
    return findings

