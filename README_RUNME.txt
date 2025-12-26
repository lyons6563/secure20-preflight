SECURE 2.0 Preflight Checker - Quick Start Guide
================================================

NOTE: This tool flags *risk* based on payroll data; it does not render legal determinations.

HOW TO USE (3 Simple Steps):
----------------------------
1. Drop your payroll CSV file into the "inbox" folder
2. Double-click "START_PRECHECKER.bat" to start processing
3. Find your results in the "preflight_outputs" folder (look for the newest timestamp folder)

No Python required when using the EXE (v5+)

DROP-FOLDER WORKFLOW:
---------------------
The tool uses a simple drop-folder system:

- inbox/          → Drop your payroll CSV files here
- processed/      → Successfully processed files are moved here automatically
- failed/         → Files that failed processing are moved here automatically
- reference/      → Place hours_history.csv here if you need LTPT checks (optional)
- preflight_outputs/ → All results are saved here in timestamped folders

HOW IT WORKS:
-------------
1. Place your payroll CSV file in the "inbox" folder
2. Run START_PRECHECKER.bat (double-click it)
3. The watcher monitors the inbox folder and processes files automatically
4. Each processed file creates a new folder in "preflight_outputs" with:
   - secure20_preflight_exceptions.csv = Detailed report of all findings
   - run_summary.txt = Summary of the processing run
5. Press Ctrl+C in the watcher window to stop monitoring

WHAT THE RESULTS MEAN:
----------------------
GREEN = Everything looks good. No action needed.

YELLOW = Review recommended. Some employees may become highly compensated 
         (potential risk flags found). Check the output CSV for details.

RED = Action required. Some employees are projected to be highly compensated 
      and need Roth-only catch-up contributions under SECURE 2.0. Review the 
      output CSV and ensure payroll is enforcing the Roth-only requirement.

SAMPLE FILES:
-------------
Try the sample files in "inbox/sample_inputs" folder to test the tool:
- These are example payroll files you can use to see how the tool works
- Drop any of these files into the "inbox" folder (not the sample_inputs subfolder) to process them

HOW TO UNDERSTAND SKIPPED CHECKS:
----------------------------------
At the end of each run, the tool prints diagnostics showing which checks ran and which were skipped.

Example diagnostics output:
=== DIAGNOSTICS ===
Config file used: configs\secure20_preflight_config.ltpt_3yr.yaml
Rules executed: RothCatchup, LTPT
Rules skipped:
  - AutoEnroll: disabled in config
===================

Common skip reasons:
- "disabled in config" = The check is turned off in your config file
- "hours_history.csv not found" = LTPT check needs reference\hours_history.csv file
- "required columns missing" = Payroll CSV doesn't have the needed columns (e.g., hire_date for auto-enroll)

REQUIREMENTS:
-------------
- Windows operating system
- No Python required when using the EXE (v5+)

For questions or support, contact your IT administrator.

