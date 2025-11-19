"""
Test script for extracting Census Building Permits data from scanned PDFs using Gemini.

This script tests extraction on a single page pair from the 1967 PDF.
"""

import os
import json
import time
import io
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
MODEL = "gemini-3-pro-preview"  # Using a stable model
PDF_PATH = Path("scans/MSA_Annual 1967.pdf")


# Define Pydantic models for structured output
class PermitRow(BaseModel):
    """A single row of building permit data."""
    line_number: str
    smsa_name: str
    # Housing units (from first page)
    total_units: str
    private_total: str
    private_1_unit: str
    private_2_units: str
    private_3_4_units: str
    private_5plus_units: str
    public_units: str
    private_structures: str
    # Valuation in thousands of dollars (from second page)
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

# Define the extraction prompt
EXTRACTION_PROMPT = """You are extracting data from scanned Census Building Permits Survey tables.

I'm showing you two consecutive pages from a 1967 report:
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
    """
    Extract specific pages from a PDF and return as bytes.

    Args:
        pdf_path: Path to the source PDF
        pages: List of page numbers (0-indexed)

    Returns:
        PDF bytes containing only the specified pages
    """
    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    for page_num in pages:
        writer.add_page(reader.pages[page_num])

    # Write to bytes buffer
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)

    return buffer.read()


def extract_page_pair(pdf_path: Path, page1: int, page2: int) -> list[dict]:
    """
    Extract data from a pair of pages (housing units + valuation).

    Args:
        pdf_path: Path to the PDF file
        page1: First page number (1-indexed, housing units)
        page2: Second page number (1-indexed, valuation)

    Returns:
        List of extracted row dictionaries
    """
    print(f"Extracting pages {page1} and {page2} from {pdf_path.name}...")

    # Extract only the two pages we need (convert to 0-indexed)
    pdf_bytes = extract_pdf_pages(pdf_path, [page1 - 1, page2 - 1])
    print(f"  Extracted {len(pdf_bytes) / 1024:.1f} KB for 2 pages")

    # Save to temp file and upload via File API
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        # Upload to File API
        uploaded_file = client.files.upload(file=tmp_path)
        print(f"  Uploaded to File API: {uploaded_file.name}")

        # Create the request with structured output
        response = client.models.generate_content(
            model=MODEL,
            contents=[EXTRACTION_PROMPT, uploaded_file],
            config=types.GenerateContentConfig(
                temperature=0.0,  # Deterministic for OCR tasks
                max_output_tokens=32768,  # Increased for large tables
                response_mime_type="application/json",
                response_schema=ExtractionResult,
            )
        )
    finally:
        # Clean up temp file
        import os as os_module
        os_module.unlink(tmp_path)

    # Parse structured response
    try:
        # First try the .parsed attribute (structured output)
        result = response.parsed
        if result is not None:
            rows = [row.model_dump() for row in result.rows]
            print(f"  Successfully extracted {len(rows)} rows (structured)")
            return rows

        # Fallback: parse JSON from text response
        print("  Note: .parsed returned None, falling back to JSON text parsing")
        response_text = response.text
        if not response_text:
            print("ERROR: Empty response from API")
            return []

        # Parse the JSON response
        data = json.loads(response_text)

        # Handle both formats: {"rows": [...]} or just [...]
        if isinstance(data, dict) and "rows" in data:
            rows = data["rows"]
        elif isinstance(data, list):
            rows = data
        else:
            print(f"ERROR: Unexpected response format: {type(data)}")
            print("Response:", response_text[:500])
            return []

        print(f"  Successfully extracted {len(rows)} rows (JSON fallback)")
        return rows

    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse JSON: {e}")
        print("Response text:", response.text[:500] if response.text else "None")
        return []
    except Exception as e:
        print(f"ERROR: Failed to parse response: {e}")
        print("Response type:", type(response))
        print("Response dir:", [attr for attr in dir(response) if not attr.startswith('_')])
        if hasattr(response, 'text'):
            print("Response text:", response.text[:500] if response.text else "None")
        return []


def parse_number(s: str) -> int | None:
    """
    Parse a number string like "1 234" or "150" into an integer.
    Returns None for "-", "(X)", or unparseable values.
    """
    if not s or s == "(X)":
        return None
    elif s.strip() == "-":
        return 0
    try:
        # Remove spaces (thousands separator) and parse
        return int(s.replace(" ", ""))
    except ValueError:
        return None


def validate_row(row: dict) -> list[str]:
    """
    Validate a single row of extracted data.

    Returns list of error messages (empty if valid).
    """
    errors = []

    # Check required fields exist
    required_fields = ["line_number", "smsa_name", "total_units", "private_total"]
    for field in required_fields:
        if field not in row or not row[field]:
            errors.append(f"Missing required field: {field}")

    # Check line_number is numeric
    if "line_number" in row:
        try:
            int(row["line_number"])
        except ValueError:
            errors.append(f"Invalid line_number: {row.get('line_number')}")

    # Parse numeric values for consistency checks
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
            # Allow small rounding differences (up to 1% or 5 units)
            tolerance = max(5, int(total_units * 0.01))
            if diff > tolerance:
                errors.append(f"Units sum mismatch: total={total_units}, private+public={expected} (diff={diff})")

    # Check: private_total ≈ sum of private unit breakdowns
    if private_total is not None:
        components = [private_1, private_2, private_34, private_5plus]
        if all(c is not None for c in components):
            component_sum = sum(components)
            diff = abs(private_total - component_sum)
            tolerance = max(5, int(private_total * 0.01))
            if diff > tolerance:
                errors.append(f"Private units breakdown mismatch: total={private_total}, sum={component_sum} (diff={diff})")

    # Check: total_valuation = private_valuation + public_valuation
    if total_val is not None and private_val is not None and public_val is not None:
        expected = private_val + public_val
        if total_val != expected:
            diff = abs(total_val - expected)
            tolerance = max(10, int(total_val * 0.01))
            if diff > tolerance:
                errors.append(f"Valuation sum mismatch: total={total_val}, private+public={expected} (diff={diff})")

    # Check: private_valuation ≈ sum of private valuation breakdowns
    if private_val is not None:
        val_components = [private_1_val, private_2_val, private_34_val, private_5plus_val]
        if all(c is not None for c in val_components):
            component_sum = sum(val_components)
            diff = abs(private_val - component_sum)
            tolerance = max(10, int(private_val * 0.01))
            if diff > tolerance:
                errors.append(f"Private valuation breakdown mismatch: total={private_val}, sum={component_sum} (diff={diff})")

    return errors

def test_gemini_basic():
    print("Running basic Gemini text test...")
    try:
        resp = client.models.generate_content(
            model=MODEL,
            contents="Say 'hello from Gemini' and nothing else."
        )
        # SDK-specific: adjust if `resp.text` or `resp.candidates` differs.
        print("Raw response:", getattr(resp, "text", resp))
    except Exception as e:
        print("Basic test error:", e)


def main():
    """Test extraction on first page pair of 1967 PDF."""

    # Check API key
    if not os.getenv("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY not set!")
        print("\nPlease set your API key using one of these methods:")
        print("1. Create a .env file with: GEMINI_API_KEY=your-key-here")
        print("2. Set environment variable: $env:GEMINI_API_KEY = 'your-key-here'")
        return

    # test_gemini_basic()
    # print("\n--- Continuing to PDF extraction test ---\n")

    # Check PDF exists
    if not PDF_PATH.exists():
        print(f"ERROR: PDF not found at {PDF_PATH}")
        return

    print("=" * 60)
    print("Testing Gemini PDF Extraction")
    print("=" * 60)
    print(f"Model: {MODEL}")
    print(f"PDF: {PDF_PATH}")
    print(f"Pages: 1-2 (first page pair)")
    print("=" * 60)

    # Extract first page pair
    start_time = time.time()
    rows = extract_page_pair(PDF_PATH, 1, 2)
    elapsed = time.time() - start_time

    print(f"\nExtraction took {elapsed:.1f} seconds")

    if not rows:
        print("No data extracted!")
        return

    # Validate rows
    print("\n" + "=" * 60)
    print("Validation Results")
    print("=" * 60)

    total_errors = 0
    for i, row in enumerate(rows):
        errors = validate_row(row)
        if errors:
            print(f"Row {i+1} (line {row.get('line_number', '?')}): {', '.join(errors)}")
            total_errors += len(errors)

    if total_errors == 0:
        print("All rows passed validation!")
    else:
        print(f"\nTotal validation errors: {total_errors}")

    # Check line number sequence
    print("\n" + "=" * 60)
    print("Line Number Sequence Check")
    print("=" * 60)

    line_numbers = []
    for row in rows:
        try:
            line_numbers.append(int(row.get("line_number", 0)))
        except ValueError:
            pass

    if line_numbers:
        # Check for gaps or duplicates
        expected = list(range(1, max(line_numbers) + 1))
        missing = set(expected) - set(line_numbers)
        duplicates = [n for n in line_numbers if line_numbers.count(n) > 1]

        if missing:
            print(f"Missing line numbers: {sorted(missing)}")
        if duplicates:
            print(f"Duplicate line numbers: {sorted(set(duplicates))}")
        if not missing and not duplicates:
            print(f"Line numbers 1-{max(line_numbers)} are complete and sequential!")

        # Check order
        if line_numbers != sorted(line_numbers):
            print("WARNING: Line numbers are not in ascending order")

    # Show sample output
    print("\n" + "=" * 60)
    print("Sample Output (first 3 rows)")
    print("=" * 60)

    for row in rows[:3]:
        print(json.dumps(row, indent=2))
        print("-" * 40)

    # Save full output for review
    output_path = Path("output")
    output_path.mkdir(exist_ok=True)

    output_file = output_path / "test_extraction_1967_pages_1_2.json"
    with open(output_file, "w") as f:
        json.dump(rows, f, indent=2)

    print(f"\nFull output saved to: {output_file}")
    print(f"Total rows extracted: {len(rows)}")


if __name__ == "__main__":
    main()
