"""
Extract Census Building Permits data from scanned PDFs using Gemini.

Processes all PDFs in scans/ directory and saves JSON results to raw_ocr/.
"""

import os
import json
import time
import io
import tempfile
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pypdf import PdfReader, PdfWriter
from pydantic import BaseModel

# Load environment variables
load_dotenv()

# Initialize client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Configuration
MODEL = "gemini-3-pro-preview"
SCANS_DIR = Path("scans")
OUTPUT_DIR = Path("raw_ocr")

# Rate limiting: 50 requests/min = 1.2 seconds between requests
REQUEST_DELAY = 1.5  # seconds between API calls


class PermitRow(BaseModel):
    """A single row of building permit data."""
    line_number: str
    smsa_name: str
    total_units: str
    private_total: str
    private_1_unit: str
    private_2_units: str
    private_3_4_units: str
    private_5plus_units: str
    public_units: str
    private_structures: str
    total_valuation: str
    private_valuation: str
    private_1_unit_val: str
    private_2_units_val: str
    private_3_4_units_val: str
    private_5plus_units_val: str
    public_valuation: str


class ExtractionResult(BaseModel):
    """Container for all extracted rows."""
    rows: list[PermitRow]


EXTRACTION_PROMPT = """You are extracting data from scanned Census Building Permits Survey tables.

I'm showing you two consecutive pages from a report:
- The first page shows "Number of housing units" data
- The second page shows "Valuation (thousands of dollars)" data

Both pages have the same rows (matched by line_number). Extract all rows from both pages and join them by line_number.

Field mapping:
- line_number: Row number from the table
- smsa_name: Metropolitan statistical area name (e.g., "ABILENE, TEX.")
- total_units, private_total, private_1_unit, private_2_units, private_3_4_units, private_5plus_units, public_units, private_structures: From housing units page
- total_valuation, private_valuation, private_1_unit_val, private_2_units_val, private_3_4_units_val, private_5plus_units_val, public_valuation: From valuation page

IMPORTANT:
- Keep all values as strings exactly as printed (e.g., "1 234", "150", "-", "(X)")
- Use "-" for dashes/missing values
- Use "(X)" for suppressed data
- Include ALL rows, including sub-rows (like "INSIDE CENTRAL CITIES", "OUTSIDE CENTRAL CITY")

Extract ALL rows from these two pages:"""


def extract_pdf_pages(pdf_path: Path, pages: list[int]) -> bytes:
    """Extract specific pages from a PDF and return as bytes."""
    reader = PdfReader(pdf_path)
    writer = PdfWriter()
    for page_num in pages:
        writer.add_page(reader.pages[page_num])
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    return buffer.read()


def get_page_count(pdf_path: Path) -> int:
    """Get total number of pages in a PDF."""
    reader = PdfReader(pdf_path)
    return len(reader.pages)


def parse_number(s: str) -> int | None:
    """Parse a number string for validation. Returns 0 for '-', None for '(X)'."""
    if not s or s == "(X)":
        return None
    elif s.strip() == "-":
        return 0
    try:
        return int(s.replace(" ", ""))
    except ValueError:
        return None


def validate_row(row: dict) -> list[str]:
    """Validate a single row. Returns list of error messages."""
    errors = []

    # Check line_number is numeric
    if "line_number" in row:
        try:
            int(row["line_number"])
        except ValueError:
            errors.append(f"Invalid line_number: {row.get('line_number')}")

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
        if total_units != expected:
            diff = abs(total_units - expected)
            tolerance = max(5, int(total_units * 0.01))
            if diff > tolerance:
                errors.append(f"Units sum: {total_units} != {expected} (diff={diff})")

    # Check: private_total ≈ sum of breakdowns
    if private_total is not None:
        components = [private_1, private_2, private_34, private_5plus]
        if all(c is not None for c in components):
            component_sum = sum(components)
            diff = abs(private_total - component_sum)
            tolerance = max(5, int(private_total * 0.01))
            if diff > tolerance:
                errors.append(f"Private units: {private_total} != {component_sum} (diff={diff})")

    # Check: total_valuation = private_valuation + public_valuation
    if total_val is not None and private_val is not None and public_val is not None:
        expected = private_val + public_val
        if total_val != expected:
            diff = abs(total_val - expected)
            tolerance = max(10, int(total_val * 0.01))
            if diff > tolerance:
                errors.append(f"Valuation sum: {total_val} != {expected} (diff={diff})")

    # Check: private_valuation ≈ sum of breakdowns
    if private_val is not None:
        val_components = [private_1_val, private_2_val, private_34_val, private_5plus_val]
        if all(c is not None for c in val_components):
            component_sum = sum(val_components)
            diff = abs(private_val - component_sum)
            tolerance = max(10, int(private_val * 0.01))
            if diff > tolerance:
                errors.append(f"Private valuation: {private_val} != {component_sum} (diff={diff})")

    return errors


def validate_page_pair(rows: list[dict], year: str, page1: int, page2: int) -> list[str]:
    """Validate all rows from a page pair. Returns list of error messages."""
    errors = []

    # Validate each row
    for row in rows:
        row_errors = validate_row(row)
        for err in row_errors:
            errors.append(f"Line {row.get('line_number', '?')}: {err}")

    # Check line number sequence
    line_numbers = []
    for row in rows:
        try:
            line_numbers.append(int(row.get("line_number", 0)))
        except ValueError:
            pass

    if line_numbers:
        expected = list(range(1, max(line_numbers) + 1))
        missing = set(expected) - set(line_numbers)
        duplicates = [n for n in line_numbers if line_numbers.count(n) > 1]

        if missing:
            errors.append(f"Missing line numbers: {sorted(missing)}")
        if duplicates:
            errors.append(f"Duplicate line numbers: {sorted(set(duplicates))}")
        if line_numbers != sorted(line_numbers):
            errors.append("Line numbers not in order")

    return errors


def extract_page_pair(pdf_path: Path, page1: int, page2: int) -> list[dict]:
    """Extract data from a pair of pages (housing units + valuation)."""
    pdf_bytes = extract_pdf_pages(pdf_path, [page1 - 1, page2 - 1])

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        uploaded_file = client.files.upload(file=tmp_path)

        response = client.models.generate_content(
            model=MODEL,
            contents=[EXTRACTION_PROMPT, uploaded_file],
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=65536,
                response_mime_type="application/json",
                response_schema=ExtractionResult,
            )
        )
    finally:
        os.unlink(tmp_path)

    # Parse response
    result = response.parsed
    if result is not None:
        return [row.model_dump() for row in result.rows]

    # Fallback to JSON text parsing
    response_text = response.text
    if not response_text:
        return []

    data = json.loads(response_text)
    if isinstance(data, dict) and "rows" in data:
        return data["rows"]
    elif isinstance(data, list):
        return data
    return []


def process_pdf(pdf_path: Path, output_dir: Path, log_file) -> dict:
    """
    Process a single PDF file, extracting all page pairs.

    Returns summary statistics.
    """
    year = pdf_path.stem.split()[-1]  # Extract year from filename
    year_dir = output_dir / year
    year_dir.mkdir(parents=True, exist_ok=True)

    page_count = get_page_count(pdf_path)
    num_pairs = page_count // 2

    print(f"\nProcessing {pdf_path.name}: {page_count} pages ({num_pairs} pairs)", flush=True)

    total_rows = 0
    extraction_errors = []
    validation_errors = []

    for i in range(num_pairs):
        page1 = i * 2 + 1
        page2 = i * 2 + 2

        output_file = year_dir / f"pages_{page1:02d}_{page2:02d}.json"

        # Skip if already processed
        if output_file.exists():
            with open(output_file) as f:
                existing = json.load(f)
            total_rows += len(existing)

            # Still validate existing files
            val_errors = validate_page_pair(existing, year, page1, page2)
            if val_errors:
                validation_errors.extend(val_errors)
                for err in val_errors:
                    log_file.write(f"{year} pages {page1}-{page2}: {err}\n")

            print(f"  Pages {page1}-{page2}: skipped ({len(existing)} rows, {len(val_errors)} validation issues)", flush=True)
            continue

        try:
            rows = extract_page_pair(pdf_path, page1, page2)

            with open(output_file, "w") as f:
                json.dump(rows, f, indent=2)

            # Validate extracted data
            val_errors = validate_page_pair(rows, year, page1, page2)
            if val_errors:
                validation_errors.extend(val_errors)
                for err in val_errors:
                    log_file.write(f"{year} pages {page1}-{page2}: {err}\n")

            total_rows += len(rows)
            print(f"  Pages {page1}-{page2}: {len(rows)} rows, {len(val_errors)} validation issues", flush=True)

        except Exception as e:
            error_msg = f"Pages {page1}-{page2}: {str(e)}"
            extraction_errors.append(error_msg)
            log_file.write(f"{year} {error_msg}\n")
            print(f"  ERROR - {error_msg}", flush=True)

        # Rate limiting
        time.sleep(REQUEST_DELAY)

    return {
        "year": year,
        "pages": page_count,
        "pairs": num_pairs,
        "rows": total_rows,
        "extraction_errors": extraction_errors,
        "validation_errors": len(validation_errors)
    }


def main():
    """Process all PDFs in the scans directory."""
    if not os.getenv("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY not set!")
        return

    # Get all PDF files
    pdf_files = sorted(SCANS_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in {SCANS_DIR}")
        return

    print(f"Found {len(pdf_files)} PDF files to process", flush=True)
    print(f"Output directory: {OUTPUT_DIR}", flush=True)

    OUTPUT_DIR.mkdir(exist_ok=True)

    # Open log file
    log_path = OUTPUT_DIR / "validation_errors.log"
    with open(log_path, "w") as log_file:
        log_file.write(f"Validation log - {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log_file.write("=" * 60 + "\n\n")

        # Process each PDF
        results = []
        for pdf_path in pdf_files:
            result = process_pdf(pdf_path, OUTPUT_DIR, log_file)
            results.append(result)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    total_rows = 0
    total_extraction_errors = 0
    total_validation_errors = 0
    for r in results:
        ext_err = len(r["extraction_errors"])
        val_err = r["validation_errors"]
        status = "OK" if ext_err == 0 and val_err == 0 else f"{ext_err} errors, {val_err} validation issues"
        print(f"  {r['year']}: {r['rows']} rows ({status})")
        total_rows += r["rows"]
        total_extraction_errors += ext_err
        total_validation_errors += val_err

    print(f"\nTotal: {total_rows} rows extracted")
    if total_extraction_errors:
        print(f"Extraction errors: {total_extraction_errors}")
    if total_validation_errors:
        print(f"Validation issues: {total_validation_errors}")
        print(f"See {log_path} for details")


if __name__ == "__main__":
    main()
