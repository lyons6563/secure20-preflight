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
- **Console summary**: `SAFE` (no violations) or `NOT SAFE` (violations detected), violation count, top employee IDs, and output file path
- **Exception CSV**: Always created at `preflight_outputs/<timestamp>/secure20_preflight_exceptions.csv` with detailed report of all detected violations and potential HCEs (headers only if no exceptions found)

### Exit Codes

- `0`: SAFE (no violations detected)
- `2`: NOT SAFE (violations detected) or Error (invalid inputs, file read errors, etc.)

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

