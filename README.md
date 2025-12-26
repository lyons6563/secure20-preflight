# SECURE 2.0 Preflight Checker
NOTE: This tool flags *risk* based on payroll data; it does not render legal determinations.

A command-line tool that performs preliminary compliance checks on payroll data to identify potential SECURE 2.0 Act violations before they occur. This MVP focuses exclusively on Phase 1 checks related to Highly Compensated Employee (HCE) catch-up contribution rules.

## Overview

The SECURE 2.0 Preflight Checker analyzes payroll data to detect:
- **Roth-only catch-up risk for HCEs**: Identifies Highly Compensated Employees making catch-up contributions exclusively to Roth accounts (prohibited under SECURE 2.0)
- **Potential HCE detection**: Flags employees who may become HCEs based on projected annual compensation

## Quick Start

### Example Command

```bash
python secure20_preflight.py --payroll inputs/secure20_payroll_demo.csv --config configs/secure20_preflight_config.example.yaml
```

### Required Arguments

- `--payroll` / `-p`: Path to payroll CSV file (required)
- `--config` / `-c`: Path to YAML configuration file (required)

### Output

The tool outputs:
- **Console summary**: Traffic-light status (GREEN/YELLOW/RED), violation count, potential issues count, top employee IDs (if applicable), and output file path
- **Exception CSV**: Always created at `preflight_outputs/<timestamp>/secure20_preflight_exceptions.csv` with a `severity` column (RED or YELLOW)

#### Traffic-Light Status

- **GREEN**: Nothing to review. No violations and no potential risk flags.
- **YELLOW**: Review recommended. Zero enforceable violations, but potential risk flags exist (e.g., `POTENTIAL_HCE`). The CSV may contain YELLOW findings even when there are 0 violations.
- **RED**: Action required. At least one enforceable violation detected. RED findings indicate HCEs making Roth-only catch-up contributions, which is prohibited under SECURE 2.0 (e.g., `ROTH_ONLY_CATCHUP_HCE`).

### Exit Codes

- `0`: GREEN or YELLOW status (no enforceable violations)
- `2`: RED status (enforceable violations detected) or Error (invalid inputs, file read errors, etc.)

## Drop-Folder Mode

For automated processing without manual command-line execution:

1. **Drop payroll CSV** into the `inbox/` folder
2. **Double-click** `START_PRECHECKER.bat` to start the watcher
3. **View results** in `preflight_outputs/<timestamp>/` folder

The watcher automatically:
- Processes each new CSV file in `inbox/`
- Moves successfully processed files to `processed/`
- Moves failed files to `failed/`
- Creates a `run_summary.txt` in each output folder with processing details

Press Ctrl+C in the watcher window to stop monitoring.

## Documentation

For complete specification and details, see [docs/SECURE20_PREFLIGHT_MVP.md](docs/SECURE20_PREFLIGHT_MVP.md).

## Project Structure

```
.
├── secure20_preflight.py          # CLI entry point
├── configs/
│   └── secure20_preflight_config.example.yaml  # Example configuration
├── inputs/
│   └── secure20_payroll_demo.csv  # Demo payroll data
├── tests/
│   └── test_secure20_preflight.py # Unit tests
└── docs/
    └── SECURE20_PREFLIGHT_MVP.md  # MVP specification
```

