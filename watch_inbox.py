#!/usr/bin/env python3
"""
Drop-Folder Mode Watcher for SECURE 2.0 Preflight Checker

Monitors inbox/ folder for new CSV files and processes them automatically.
"""

import subprocess
import sys
import time
import shutil
import os
from pathlib import Path
from datetime import datetime
import re
import yaml
import traceback
import io
from contextlib import redirect_stdout, redirect_stderr

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
    # Detect frozen vs non-frozen
    frozen = getattr(sys, "frozen", False)
    
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
        if frozen:
            # EXE mode: run in-process
            from secure20_preflight import main as preflight_main
            
            # Build argv list identical to CLI args
            argv = [
                'secure20_preflight.py',
                '--payroll', str(csv_file),
                '--config', str(config_path)
            ]
            
            # Add --hours flag if hours file exists
            if hours_file_exists:
                argv.extend(['--hours', str(HOURS_PATH)])
            
            # Temporarily set sys.argv
            old_argv = sys.argv
            sys.argv = argv
            
            # Capture stdout and stderr
            stdout_capture = io.StringIO()
            stderr_capture = io.StringIO()
            returncode = 2  # Default to error
            
            try:
                with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                    preflight_main()
                    returncode = 0  # Should not reach here (main() calls sys.exit), but just in case
            except SystemExit as e:
                # main() calls sys.exit(exit_code), which raises SystemExit
                returncode = e.code if e.code is not None else 0
            finally:
                # Restore sys.argv
                sys.argv = old_argv
            
            # Get captured output
            output_text = stdout_capture.getvalue()
            stderr_text = stderr_capture.getvalue()
            
            result = type('Result', (), {
                'stdout': output_text,
                'stderr': stderr_text,
                'returncode': returncode
            })()
        else:
            # Dev mode: use subprocess (keep existing behavior)
            cmd = [
                sys.executable,
                'secure20_preflight.py',
                '--payroll', str(csv_file),
                '--config', str(config_path)
            ]
            
            # Add --hours flag if hours file exists
            if hours_file_exists:
                cmd.extend(['--hours', str(HOURS_PATH)])
            
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
        
        # Move file based on exit code (with existence check)
        if result.returncode == 0:  # SAFE
            if csv_file.exists():
                dest = Path('processed') / csv_file.name
                shutil.move(str(csv_file), str(dest))
                print(f"Processed: {csv_file.name} -> processed/ (SAFE)")
            else:
                print(f"WARNING: {csv_file.name} no longer exists, skipping move to processed/")
            return True
        elif result.returncode == 2:  # NOT SAFE or error
            # Check if it's actually NOT SAFE (violations) or an error
            if parsed['status'] == 'NOT SAFE':
                if csv_file.exists():
                    dest = Path('processed') / csv_file.name
                    shutil.move(str(csv_file), str(dest))
                    print(f"Processed: {csv_file.name} -> processed/ (NOT SAFE)")
                else:
                    print(f"WARNING: {csv_file.name} no longer exists, skipping move to processed/")
                return True
            else:
                # It's an error
                if csv_file.exists():
                    dest = Path('failed') / csv_file.name
                    shutil.move(str(csv_file), str(dest))
                    print(f"Failed: {csv_file.name} -> failed/ (Error)")
                else:
                    print(f"WARNING: {csv_file.name} no longer exists, skipping move to failed/")
                return False
        else:
            # Unknown exit code, treat as error
            if csv_file.exists():
                dest = Path('failed') / csv_file.name
                shutil.move(str(csv_file), str(dest))
                print(f"Failed: {csv_file.name} -> failed/ (Unknown exit code: {result.returncode})")
            else:
                print(f"WARNING: {csv_file.name} no longer exists, skipping move to failed/")
            return False
            
    except subprocess.TimeoutExpired:
        if csv_file.exists():
            dest = Path('failed') / csv_file.name
            shutil.move(str(csv_file), str(dest))
            print(f"Failed: {csv_file.name} -> failed/ (Timeout)")
        else:
            print(f"WARNING: {csv_file.name} no longer exists, skipping move to failed/")
        return False
    except Exception as e:
        if csv_file.exists():
            dest = Path('failed') / csv_file.name
            shutil.move(str(csv_file), str(dest))
            print(f"Failed: {csv_file.name} -> failed/ (Exception: {e})")
        else:
            print(f"WARNING: {csv_file.name} no longer exists, skipping move to failed/")
        return False


def wait_for_file_stable(file_path: Path, max_wait: float = 30.0) -> bool:
    """Wait for file size to stabilize (2 checks, 0.5s apart, max 30s)."""
    if not file_path.exists():
        return False
    
    start_time = time.time()
    
    # First check
    try:
        prev_size = file_path.stat().st_size
    except (OSError, FileNotFoundError):
        return False
    
    # Wait 0.5s and check again
    while (time.time() - start_time) < max_wait:
        time.sleep(0.5)
        if not file_path.exists():
            return False
        try:
            current_size = file_path.stat().st_size
            if current_size == prev_size:
                return True  # Size stabilized (2 checks match)
            prev_size = current_size
        except (OSError, FileNotFoundError):
            return False
    
    return False  # Timeout reached


def watch_inbox():
    """Main watcher loop that monitors inbox/ for new CSV files."""
    # Determine base directory: EXE folder when frozen, else script folder
    if getattr(sys, 'frozen', False):
        base_dir = Path(sys.executable).parent
    else:
        base_dir = Path(__file__).parent
    
    # Change to base directory so relative paths in process_file work correctly
    os.chdir(base_dir)
    
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
            # Poll every 1s: scan inbox root for *.csv
            csv_files = list(inbox_path.glob('*.csv'))
            
            for csv_file in csv_files:
                # Skip if already processed
                if csv_file.name in processed_files:
                    continue
                
                # Wait for file size to stabilize
                if not wait_for_file_stable(csv_file):
                    print(f"WARNING: {csv_file.name} did not stabilize within timeout, processing anyway...")
                
                # Process file in try/except
                file_name = csv_file.name
                file_stem = csv_file.stem
                try:
                    success = process_file(csv_file)
                    if success:
                        print(f"PROCESSED: {file_name}")
                    else:
                        print(f"FAILED: {file_name}")
                    processed_files.add(file_name)
                except Exception as e:
                    # On exception: move CSV to failed/ and write error file
                    try:
                        if csv_file.exists():
                            dest = failed_path / file_name
                            shutil.move(str(csv_file), str(dest))
                        error_file = failed_path / f"{file_stem}__error.txt"
                        with open(error_file, 'w', encoding='utf-8') as f:
                            f.write(f"Exception processing {file_name}:\n\n")
                            f.write(traceback.format_exc())
                        print(f"FAILED: {file_name}")
                        processed_files.add(file_name)
                    except Exception as move_error:
                        print(f"ERROR: Failed to move {file_name} to failed/: {move_error}")
            
            # Sleep for 1 second before checking again
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\nWatcher stopped by user.")
        sys.exit(0)


if __name__ == '__main__':
    watch_inbox()

