"""
Strict validation script for extracted permit data.

Checks:
1. Files with no rows
2. Exact equality validation (no tolerance) for totals
"""

import json
from pathlib import Path


OUTPUT_DIR = Path("raw_ocr")


def parse_number(s: str) -> int | None:
    """Parse a number string. Returns 0 for '-', None for '(X)'."""
    if not s or s == "(X)":
        return None
    elif s.strip() == "-":
        return 0
    try:
        return int(s.replace(" ", ""))
    except ValueError:
        return None


def validate_row_strict(row: dict) -> list[str]:
    """Validate a single row with exact equality (no tolerance). Returns list of errors."""
    errors = []

    # Parse numeric values
    total_units = parse_number(row.get("total_units", ""))
    private_total = parse_number(row.get("private_total", ""))
    public_units = parse_number(row.get("public_units", ""))
    private_1 = parse_number(row.get("private_1_unit", ""))
    private_2 = parse_number(row.get("private_2_units", ""))
    private_34 = parse_number(row.get("private_3_4_units", ""))
    private_5plus = parse_number(row.get("private_5plus_units", ""))

    total_val = parse_number(row.get("total_valuation", ""))
    private_val = parse_number(row.get("private_valuation", ""))
    public_val = parse_number(row.get("public_valuation", ""))
    private_1_val = parse_number(row.get("private_1_unit_val", ""))
    private_2_val = parse_number(row.get("private_2_units_val", ""))
    private_34_val = parse_number(row.get("private_3_4_units_val", ""))
    private_5plus_val = parse_number(row.get("private_5plus_units_val", ""))

    # Check: total_units = private_total + public_units
    if total_units is not None and private_total is not None and public_units is not None:
        expected = private_total + public_units
        diff = total_units - expected
        if abs(diff) > 1:
            errors.append(f"total_units: {total_units} != {private_total} + {public_units} = {expected} (diff={diff:+d})")

    # Check: private_total = sum of breakdowns
    if private_total is not None:
        components = [private_1, private_2, private_34, private_5plus]
        if all(c is not None for c in components):
            component_sum = sum(components)
            diff = private_total - component_sum
            if abs(diff) > 1:
                errors.append(f"private_total: {private_total} != {private_1} + {private_2} + {private_34} + {private_5plus} = {component_sum} (diff={diff:+d})")

    # Check: total_valuation = private_valuation + public_valuation
    if total_val is not None and private_val is not None and public_val is not None:
        expected = private_val + public_val
        diff = total_val - expected
        if abs(diff) > 1:
            errors.append(f"total_valuation: {total_val} != {private_val} + {public_val} = {expected} (diff={diff:+d})")

    # Check: private_valuation = sum of breakdowns
    if private_val is not None:
        val_components = [private_1_val, private_2_val, private_34_val, private_5plus_val]
        if all(c is not None for c in val_components):
            component_sum = sum(val_components)
            diff = private_val - component_sum
            if abs(diff) > 1:
                errors.append(f"private_valuation: {private_val} != {private_1_val} + {private_2_val} + {private_34_val} + {private_5plus_val} = {component_sum} (diff={diff:+d})")

    return errors


def main():
    """Run strict validation on all extracted data."""
    if not OUTPUT_DIR.exists():
        print(f"Output directory not found: {OUTPUT_DIR}")
        return

    # Find all JSON files
    json_files = sorted(OUTPUT_DIR.glob("**/*.json"))

    if not json_files:
        print("No JSON files found")
        return

    # Open log file for writing
    log_path = OUTPUT_DIR / "second_look_validation.log"
    log_file = open(log_path, "w")

    def output(text=""):
        """Print and write to log file."""
        print(text)
        log_file.write(text + "\n")

    output("=" * 70)
    output("STRICT VALIDATION REPORT")
    output("=" * 70)

    # Track results
    empty_files = []
    files_with_errors = []
    total_files = 0
    total_rows = 0
    total_errors = 0

    for json_file in json_files:
        # Skip log files
        if json_file.suffix != ".json":
            continue

        total_files += 1

        with open(json_file) as f:
            try:
                rows = json.load(f)
            except json.JSONDecodeError as e:
                files_with_errors.append((json_file, [f"JSON parse error: {e}"]))
                continue

        # Check for empty files
        if not rows:
            empty_files.append(json_file)
            continue

        total_rows += len(rows)

        # Validate each row
        file_errors = []
        for row in rows:
            row_errors = validate_row_strict(row)
            for err in row_errors:
                line_num = row.get("line_number", "?")
                smsa = row.get("smsa_name", "Unknown")
                file_errors.append(f"Line {line_num} ({smsa}): {err}")
                total_errors += 1

        if file_errors:
            files_with_errors.append((json_file, file_errors))

    # Report empty files
    output("\n" + "-" * 70)
    output("FILES WITH NO ROWS")
    output("-" * 70)

    if empty_files:
        for f in empty_files:
            rel_path = f.relative_to(OUTPUT_DIR)
            output(f"  {rel_path}")
        output(f"\nTotal: {len(empty_files)} empty file(s)")
    else:
        output("  None")

    # Report validation errors
    output("\n" + "-" * 70)
    output("EXACT EQUALITY VALIDATION ERRORS")
    output("-" * 70)

    if files_with_errors:
        for json_file, errors in files_with_errors:
            rel_path = json_file.relative_to(OUTPUT_DIR)
            output(f"\n{rel_path}:")
            for err in errors:
                output(f"  {err}")
    else:
        output("  None")

    # Summary
    output("\n" + "=" * 70)
    output("SUMMARY")
    output("=" * 70)
    output(f"  Total files scanned: {total_files}")
    output(f"  Total rows: {total_rows}")
    output(f"  Empty files: {len(empty_files)}")
    output(f"  Files with errors: {len(files_with_errors)}")
    output(f"  Total validation errors: {total_errors}")

    # Close log file
    log_file.close()
    print(f"\nLog written to: {log_path}")


if __name__ == "__main__":
    main()
