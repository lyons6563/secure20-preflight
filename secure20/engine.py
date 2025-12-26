"""
SECURE 2.0 Preflight Engine

Main engine that loads payroll data, applies rules, and generates findings.
"""

import csv
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List, Tuple

from secure20.rules import roth_catchup, auto_enroll


def _parse_decimal(value: str, field_name: str, row_num: int) -> Decimal:
    """Parse a decimal value from CSV, raising clear errors on failure."""
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field_name} must be a valid number")


def _parse_date(value: str, field_name: str, row_num: int) -> date:
    """Parse a date value from CSV (YYYY-MM-DD format), raising clear errors on failure."""
    try:
        return datetime.strptime(value.strip(), '%Y-%m-%d').date()
    except ValueError:
        raise ValueError(f"{field_name} must be in YYYY-MM-DD format")


def load_payroll_data(payroll_path: Path) -> List[Dict]:
    """
    Load and validate payroll CSV file.
    
    Args:
        payroll_path: Path to payroll CSV file
        
    Returns:
        List of dictionaries, each representing a payroll record
        
    Raises:
        SystemExit(2): If CSV file cannot be read or is invalid
    """
    required_columns = ['employee_id', 'employee_name', 'gross_pay', 
                       'ytd_gross_pay', 'pay_period_start', 'pay_period_end']
    
    try:
        with open(payroll_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            # Check for required columns
            if not reader.fieldnames:
                print("Error: CSV file is empty or has no header row", file=sys.stderr)
                sys.exit(2)
            
            missing_columns = [col for col in required_columns if col not in reader.fieldnames]
            if missing_columns:
                print(f"Error: Missing required CSV columns: {', '.join(missing_columns)}", file=sys.stderr)
                sys.exit(2)
            
            records = []
            for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
                try:
                    # Validate and convert required fields
                    record = {
                        'employee_id': str(row['employee_id']).strip(),
                        'employee_name': str(row['employee_name']).strip(),
                        'gross_pay': _parse_decimal(row['gross_pay'], 'gross_pay', row_num),
                        'ytd_gross_pay': _parse_decimal(row['ytd_gross_pay'], 'ytd_gross_pay', row_num),
                        'pay_period_start': _parse_date(row['pay_period_start'], 'pay_period_start', row_num),
                        'pay_period_end': _parse_date(row['pay_period_end'], 'pay_period_end', row_num),
                    }
                    
                    # Validate optional fields
                    catch_up_contribution = row.get('catch_up_contribution', '').strip()
                    if catch_up_contribution:
                        record['catch_up_contribution'] = _parse_decimal(
                            catch_up_contribution, 'catch_up_contribution', row_num
                        )
                    else:
                        record['catch_up_contribution'] = Decimal('0')
                    
                    catch_up_type = row.get('catch_up_type', '').strip()
                    if catch_up_type:
                        if catch_up_type not in ['Roth', 'Traditional']:
                            print(f"Error: Row {row_num}: catch_up_type must be 'Roth' or 'Traditional'", file=sys.stderr)
                            sys.exit(2)
                        record['catch_up_type'] = catch_up_type
                    else:
                        record['catch_up_type'] = None
                    
                    # Optional auto-enroll fields (added if present in CSV)
                    if 'hire_date' in reader.fieldnames:
                        record['hire_date'] = row.get('hire_date', '').strip()
                    if 'deferral_rate' in reader.fieldnames:
                        record['deferral_rate'] = row.get('deferral_rate', '').strip()
                    if 'deferral_start_date' in reader.fieldnames:
                        record['deferral_start_date'] = row.get('deferral_start_date', '').strip()
                    
                    # Validate dates are in order
                    if record['pay_period_start'] > record['pay_period_end']:
                        print(f"Error: Row {row_num}: pay_period_start must be <= pay_period_end", file=sys.stderr)
                        sys.exit(2)
                    
                    # Validate non-negative amounts
                    if record['gross_pay'] < 0:
                        print(f"Error: Row {row_num}: gross_pay must be non-negative", file=sys.stderr)
                        sys.exit(2)
                    if record['ytd_gross_pay'] < 0:
                        print(f"Error: Row {row_num}: ytd_gross_pay must be non-negative", file=sys.stderr)
                        sys.exit(2)
                    if record['catch_up_contribution'] < 0:
                        print(f"Error: Row {row_num}: catch_up_contribution must be non-negative", file=sys.stderr)
                        sys.exit(2)
                    
                    records.append(record)
                    
                except (ValueError, KeyError) as e:
                    print(f"Error: Row {row_num}: {e}", file=sys.stderr)
                    sys.exit(2)
            
            if not records:
                print("Error: CSV file contains no data rows", file=sys.stderr)
                sys.exit(2)
            
            return records
            
    except IOError as e:
        print(f"Error: Cannot read payroll file: {e}", file=sys.stderr)
        sys.exit(2)


def write_exception_csv(exceptions: List[Dict], output_path: Path) -> None:
    """
    Write exception records to CSV file.
    
    Args:
        exceptions: List of exception dictionaries
        output_path: Path to output CSV file
    """
    fieldnames = [
        'employee_id',
        'employee_name',
        'violation_type',
        'violation_description',
        'projected_annual_compensation',
        'catch_up_amount',
        'catch_up_type',
        'pay_period_start',
        'pay_period_end',
        'severity'
    ]
    
    try:
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            # Add severity to each exception
            for exc in exceptions:
                if exc['violation_type'] in ['ROTH_ONLY_CATCHUP_HCE', 'AUTO_ENROLL_MISS']:
                    exc['severity'] = 'RED'
                else:
                    exc['severity'] = 'YELLOW'
                writer.writerow(exc)
    except IOError as e:
        print(f"Error: Cannot write exception CSV file: {e}", file=sys.stderr)
        sys.exit(2)


def run_engine(payroll_data: List[Dict], config: Dict) -> Tuple[str, int, List[Dict], int, int]:
    """
    Run the preflight engine with all rules.
    
    Args:
        payroll_data: List of payroll records
        config: Configuration dictionary
        
    Returns:
        Tuple of (status, exit_code, all_findings, violation_count, potential_count)
    """
    # Apply all rules
    all_findings = []
    
    # Rule 1: Roth-only catch-up requirement (RED findings)
    roth_violations = roth_catchup.check_roth_only_catchup_hce(payroll_data, config)
    all_findings.extend(roth_violations)
    
    # Rule 2: Potential HCE detection (YELLOW findings)
    potential_hces = roth_catchup.check_potential_hce(payroll_data, config)
    all_findings.extend(potential_hces)
    
    # Rule 3: Auto-enrollment and escalation checks
    auto_enroll_misses = auto_enroll.check_auto_enroll_miss(payroll_data, config)
    all_findings.extend(auto_enroll_misses)
    
    auto_enroll_below_default = auto_enroll.check_auto_enroll_below_default(payroll_data, config)
    all_findings.extend(auto_enroll_below_default)
    
    escalation_misses = auto_enroll.check_escalation_miss(payroll_data, config)
    all_findings.extend(escalation_misses)
    
    # Count actual violations (RED findings: ROTH_ONLY_CATCHUP_HCE, AUTO_ENROLL_MISS)
    actual_violations = [v for v in all_findings if v['violation_type'] in ['ROTH_ONLY_CATCHUP_HCE', 'AUTO_ENROLL_MISS']]
    violation_count = len(actual_violations)
    # Count potential issues (YELLOW findings: POTENTIAL_HCE, AUTO_ENROLL_BELOW_DEFAULT, ESCALATION_MISS)
    potential_count = len([v for v in all_findings if v['violation_type'] in ['POTENTIAL_HCE', 'AUTO_ENROLL_BELOW_DEFAULT', 'ESCALATION_MISS']])
    
    # Determine traffic-light status
    if violation_count > 0:
        status = "RED"
        exit_code = 2
    elif potential_count > 0:
        status = "YELLOW"
        exit_code = 0
    else:
        status = "GREEN"
        exit_code = 0
    
    return status, exit_code, all_findings, violation_count, potential_count, actual_violations, potential_hces

