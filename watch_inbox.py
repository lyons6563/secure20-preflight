#!/usr/bin/env python3
"""
Drop-Folder Mode Watcher for SECURE 2.0 Preflight Checker

Monitors inbox/ folder for new CSV files and processes them automatically.
"""

import subprocess
import sys
import time
import shutil
from pathlib import Path
from datetime import datetime
import re
import yaml

# Demo mode selection: "catchup" | "auto_enroll" | "ltpt" | "full"
# Controls which config file is used automatically in drop-folder mode
DEMO_MODE = "catchup"  # default: catch-up checks only


def find_latest_output_folder():
    """Find the most recently created preflight_outputs timestamp folder."""
    output_base = Path('preflight_outputs')
    if not output_base.exists():
        return None
    
    folders = [d for d in output_base.iterdir() if d.is_dir()]
    if not folders:
        return None
    
    # Sort by modification time, most recent first
    folders.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return folders[0]


def parse_preflight_output(output_text):
    """Parse the console output from secure20_preflight.py."""
    result = {
        'status': 'UNKNOWN',
        'red_findings': 0,
        'yellow_findings': 0,
        'top_employee_ids': '',
        'output_csv_path': ''
    }
    
    lines = output_text.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith('STATUS:'):
            result['status'] = line.replace('STATUS: ', '').strip()
        elif line.startswith('RED Findings:'):
            match = re.search(r'RED Findings:\s*(\d+)', line)
            if match:
                result['red_findings'] = int(match.group(1))
        elif line.startswith('YELLOW Findings:'):
            match = re.search(r'YELLOW Findings:\s*(\d+)', line)
            if match:
                result['yellow_findings'] = int(match.group(1))
        elif line.startswith('Top employee IDs:'):
            result['top_employee_ids'] = line.replace('Top employee IDs: ', '')
        elif line.startswith('Output:'):
            result['output_csv_path'] = line.replace('Output: ', '')
    
    # Legacy compatibility: map to old status format
    if result['status'] == 'GREEN':
        result['status'] = 'SAFE'
    elif result['status'] == 'RED':
        result['status'] = 'NOT SAFE'
    elif result['status'] == 'YELLOW':
        result['status'] = 'SAFE'  # YELLOW is still considered "safe" (no violations)
    
    return result


def get_config_path(demo_mode: str) -> Path:
    """Get config file path based on demo mode."""
    config_map = {
        'catchup': 'configs/secure20_preflight_config.example.yaml',
        'auto_enroll': 'configs/secure20_preflight_config.auto_enroll.yaml',
        'ltpt': 'configs/secure20_preflight_config.ltpt_3yr.yaml',
        'full': 'configs/secure20_preflight_config.full.yaml'
    }
    
    config_name = config_map.get(demo_mode.lower(), config_map['catchup'])
    return Path(config_name)


def process_file(csv_file: Path):
    """Process a single CSV file through the preflight checker."""
    # Select config based on DEMO_MODE
    config_path = get_config_path(DEMO_MODE)
    HOURS_PATH = Path('reference/hours_history.csv')
    
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        print(f"       DEMO_MODE is set to: {DEMO_MODE}", file=sys.stderr)
        return False
    
    # Check if LTPT is enabled in config
    ltpt_enabled = False
    hours_file_exists = HOURS_PATH.exists()
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            ltpt_enabled = config.get('ltpt_enabled', False)
    except Exception as e:
        print(f"Warning: Could not read config file: {e}", file=sys.stderr)
    
    # Check LTPT configuration for ltpt and full modes
    if DEMO_MODE.lower() in ['ltpt', 'full']:
        if ltpt_enabled and not hours_file_exists:
            print("LTPT enabled but reference/hours_history.csv not found; skipping LTPT.", file=sys.stderr)
    
    try:
        # Run secure20_preflight.py
        cmd = [
            sys.executable,
            'secure20_preflight.py',
            '--payroll', str(csv_file),
            '--config', str(config_path)
        ]
        
        # Add --hours flag if hours file exists
        if hours_file_exists:
            cmd.extend(['--hours', str(HOURS_PATH)])
        
        # Note: config_path is passed via --config flag, which secure20_preflight.py will use
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        # Parse output
        output_text = result.stdout
        parsed = parse_preflight_output(output_text)
        
        # Find the latest output folder (created by secure20_preflight.py)
        output_folder = find_latest_output_folder()
        
        if output_folder:
            # Write run summary
            summary_path = output_folder / 'run_summary.txt'
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write(f"Input filename: {csv_file.name}\n")
                f.write(f"Status: {parsed['status']}\n")
                f.write(f"RED Findings: {parsed['red_findings']}\n")
                f.write(f"YELLOW Findings: {parsed['yellow_findings']}\n")
                if parsed['top_employee_ids']:
                    f.write(f"Top employee IDs: {parsed['top_employee_ids']}\n")
                f.write(f"Output CSV path: {parsed['output_csv_path']}\n")
                f.write(f"\n--- Full Console Output ---\n")
                f.write(output_text)
                if result.stderr:
                    f.write(f"\n--- Standard Error ---\n")
                    f.write(result.stderr)
        
        # Move file based on exit code
        if result.returncode == 0:  # SAFE
            dest = Path('processed') / csv_file.name
            shutil.move(str(csv_file), str(dest))
            print(f"Processed: {csv_file.name} -> processed/ (SAFE)")
            return True
        elif result.returncode == 2:  # NOT SAFE or error
            # Check if it's actually NOT SAFE (violations) or an error
            if parsed['status'] == 'NOT SAFE':
                dest = Path('processed') / csv_file.name
                shutil.move(str(csv_file), str(dest))
                print(f"Processed: {csv_file.name} -> processed/ (NOT SAFE)")
                return True
            else:
                # It's an error
                dest = Path('failed') / csv_file.name
                shutil.move(str(csv_file), str(dest))
                print(f"Failed: {csv_file.name} -> failed/ (Error)")
                return False
        else:
            # Unknown exit code, treat as error
            dest = Path('failed') / csv_file.name
            shutil.move(str(csv_file), str(dest))
            print(f"Failed: {csv_file.name} -> failed/ (Unknown exit code: {result.returncode})")
            return False
            
    except subprocess.TimeoutExpired:
        dest = Path('failed') / csv_file.name
        shutil.move(str(csv_file), str(dest))
        print(f"Failed: {csv_file.name} -> failed/ (Timeout)")
        return False
    except Exception as e:
        dest = Path('failed') / csv_file.name
        shutil.move(str(csv_file), str(dest))
        print(f"Failed: {csv_file.name} -> failed/ (Exception: {e})")
        return False


def watch_inbox():
    """Main watcher loop that monitors inbox/ for new CSV files."""
    inbox_path = Path('inbox')
    processed_path = Path('processed')
    failed_path = Path('failed')
    processed_files = set()
    
    # Ensure runtime folders exist
    inbox_path.mkdir(exist_ok=True)
    processed_path.mkdir(exist_ok=True)
    failed_path.mkdir(exist_ok=True)
    
    print("Watching inbox/ for new CSV files...")
    print("Press Ctrl+C to stop.\n")
    
    try:
        while True:
            # Check for new CSV files
            csv_files = list(inbox_path.glob('*.csv'))
            
            for csv_file in csv_files:
                # Skip if already processed
                if csv_file.name in processed_files:
                    continue
                
                print(f"Found new file: {csv_file.name}")
                process_file(csv_file)
                processed_files.add(csv_file.name)
            
            # Sleep for 2 seconds before checking again
            time.sleep(2)
            
    except KeyboardInterrupt:
        print("\n\nWatcher stopped by user.")
        sys.exit(0)


if __name__ == '__main__':
    watch_inbox()

