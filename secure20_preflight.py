#!/usr/bin/env python3
"""
SECURE 2.0 Preflight Checker - CLI Entry Point

Performs Phase 1 compliance checks on payroll data to identify potential
SECURE 2.0 Act violations related to HCE catch-up contribution rules.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict
import yaml


def load_config(config_path: Path) -> Dict:
    """
    Load and validate YAML configuration file.
    
    Args:
        config_path: Path to YAML configuration file
        
    Returns:
        Dictionary containing configuration parameters
        
    Raises:
        SystemExit(2): If config file cannot be read or is invalid
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"Error: Invalid YAML format in config file: {e}", file=sys.stderr)
        sys.exit(2)
    except IOError as e:
        print(f"Error: Cannot read config file: {e}", file=sys.stderr)
        sys.exit(2)
    
    if not isinstance(config, dict):
        print("Error: Config file must contain a YAML dictionary", file=sys.stderr)
        sys.exit(2)
    
    # Validate required keys
    required_keys = ['hce_threshold', 'catch_up', 'annualization']
    for key in required_keys:
        if key not in config:
            print(f"Error: Missing required config key: {key}", file=sys.stderr)
            sys.exit(2)
    
    # Validate hce_threshold
    hce = config['hce_threshold']
    if 'current_year' not in hce or 'compensation_limit' not in hce:
        print("Error: hce_threshold must contain current_year and compensation_limit", file=sys.stderr)
        sys.exit(2)
    
    try:
        current_year = int(hce['current_year'])
        compensation_limit = float(hce['compensation_limit'])
        if current_year < 2000 or current_year > 2100:
            print("Error: current_year must be a valid year", file=sys.stderr)
            sys.exit(2)
        if compensation_limit <= 0:
            print("Error: compensation_limit must be positive", file=sys.stderr)
            sys.exit(2)
    except (ValueError, TypeError):
        print("Error: Invalid hce_threshold values (must be numeric)", file=sys.stderr)
        sys.exit(2)
    
    # Validate catch_up
    catch_up = config['catch_up']
    if 'roth_only_risk_year' not in catch_up:
        print("Error: catch_up must contain roth_only_risk_year", file=sys.stderr)
        sys.exit(2)
    
    try:
        roth_only_risk_year = int(catch_up['roth_only_risk_year'])
        if roth_only_risk_year < 2000 or roth_only_risk_year > 2100:
            print("Error: roth_only_risk_year must be a valid year", file=sys.stderr)
            sys.exit(2)
    except (ValueError, TypeError):
        print("Error: Invalid roth_only_risk_year (must be numeric)", file=sys.stderr)
        sys.exit(2)
    
    # Validate annualization
    annualization = config['annualization']
    if 'method' not in annualization:
        print("Error: annualization must contain method", file=sys.stderr)
        sys.exit(2)
    
    valid_methods = ['gross', 'ytd', 'gross_or_ytd']
    if annualization['method'] not in valid_methods:
        print(f"Error: annualization.method must be one of: {', '.join(valid_methods)}", file=sys.stderr)
        sys.exit(2)
    
    return config


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="SECURE 2.0 Preflight Checker - Phase 1 compliance checks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  secure20-preflight --payroll data/payroll.csv --config config.yaml
  secure20-preflight -p payroll.csv -c config.yaml -o exceptions.csv
        """
    )
    
    parser.add_argument(
        "--payroll", "-p",
        type=str,
        required=True,
        help="Path to payroll CSV file"
    )
    
    parser.add_argument(
        "--config", "-c",
        type=str,
        required=True,
        help="Path to YAML configuration file"
    )
    
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="exceptions.csv",
        help="Path to exception CSV output file (default: exceptions.csv)"
    )
    
    parser.add_argument(
        "--hours", "-hhrs",
        type=str,
        default=None,
        help="Path to hours history CSV file (optional, enables LTPT eligibility checks)"
    )
    
    parser.add_argument(
        "--version", "-v",
        action="version",
        version="SECURE 2.0 Preflight Checker 1.0.0"
    )
    
    args = parser.parse_args()
    
    # Validate input file paths
    payroll_path = Path(args.payroll)
    config_path = Path(args.config)
    output_path = Path(args.output)
    hours_path = Path(args.hours) if args.hours else None
    
    if not payroll_path.exists():
        print(f"Error: Payroll file not found: {payroll_path}", file=sys.stderr)
        sys.exit(2)
    
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(2)
    
    if hours_path and not hours_path.exists():
        print(f"Error: Hours history file not found: {hours_path}", file=sys.stderr)
        sys.exit(2)
    
    try:
        # Load configuration
        config = load_config(config_path)
        
        # Import engine
        from secure20.engine import load_payroll_data, load_hours_history, run_engine, write_exception_csv
        
        # Load payroll data
        payroll_data = load_payroll_data(payroll_path)
        
        # Load hours history if provided
        hours_data = None
        if hours_path:
            hours_data = load_hours_history(hours_path)
        
        # Run engine with all rules
        status, exit_code, all_findings, violation_count, potential_count, actual_violations, potential_hces = run_engine(payroll_data, config, hours_data)
        
        # Create timestamped output directory (includes milliseconds for uniqueness)
        now = datetime.now()
        timestamp = now.strftime('%Y%m%d_%H%M%S') + f"_{now.microsecond // 1000:03d}"
        output_dir = Path('preflight_outputs') / timestamp
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Always write exception CSV (even if empty)
        output_csv_path = output_dir / 'secure20_preflight_exceptions.csv'
        write_exception_csv(all_findings, output_csv_path)
        
        # Print results
        print(f"STATUS: {status}", file=sys.stdout)
        print(f"RED Findings: {violation_count}", file=sys.stdout)
        print(f"YELLOW Findings: {potential_count}", file=sys.stdout)
        
        # Get top 10 employee IDs (only for RED or YELLOW)
        if status in ["RED", "YELLOW"]:
            employee_ids = [v['employee_id'] for v in actual_violations]
            # Add potential HCE IDs if we have fewer than 10
            if len(employee_ids) < 10:
                potential_ids = [v['employee_id'] for v in potential_hces 
                               if v['employee_id'] not in employee_ids]
                employee_ids.extend(potential_ids[:10 - len(employee_ids)])
            
            top_10 = employee_ids[:10]
            if top_10:
                print(f"Top employee IDs: {', '.join(top_10)}", file=sys.stdout)
        
        print(f"Output: {output_csv_path}", file=sys.stdout)
        sys.exit(exit_code)
            
    except KeyboardInterrupt:
        print("\nError: Interrupted by user", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()

