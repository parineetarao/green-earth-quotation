"""
Step 8 — Convert a generated .docx quotation into a clean PDF, ready to
send or attach to the review queue.

WHY LIBREOFFICE HEADLESS:
It's a free, well-established way to get an accurate Word -> PDF
conversion from a script, without needing MS Word installed or a paid
conversion API. "Headless" means it runs with no visible window, driven
entirely from the command line -- exactly what an automated pipeline
needs.

HOW IT'S CALLED:
This shells out to the real `soffice` command-line tool via Python's
subprocess module, rather than using a Python PDF library directly --
LibreOffice's own rendering is what correctly preserves the real Word
template's fonts, tables, and layout, which is worth more here than
avoiding an external process call.
"""

import shutil
import subprocess
import sys
from pathlib import Path

# On Windows, Python's subprocess module doesn't always resolve a bare
# command name ("soffice") from PATH the same way a shell like PowerShell
# does -- this caused a real FileNotFoundError even though "soffice
# --version" worked fine when typed directly into the terminal. To avoid
# depending on that inconsistent resolution, we search for the real
# executable path ourselves, checking PATH first and then the standard
# Windows/Mac/Linux install locations as a fallback.
KNOWN_SOFFICE_LOCATIONS = [
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/bin/soffice",
    "/usr/local/bin/soffice",
]


def find_soffice_executable() -> str:
    """
    Return a real, usable path to the soffice executable, or raise a
    clear error if it genuinely can't be found anywhere.
    """
    which_result = shutil.which("soffice") or shutil.which("soffice.exe")
    if which_result:
        return which_result

    for candidate in KNOWN_SOFFICE_LOCATIONS:
        if Path(candidate).exists():
            return candidate

    raise RuntimeError(
        "Could not find the 'soffice' executable anywhere -- checked PATH "
        f"and these locations: {KNOWN_SOFFICE_LOCATIONS}. "
        "LibreOffice needs to be installed. Download it from "
        "https://www.libreoffice.org/download/download/ if it isn't "
        "installed yet, or tell me the real install path if it's "
        "somewhere else on your machine."
    )


def convert_docx_to_pdf(docx_path: Path, output_dir: Path | None = None, timeout_seconds: int = 60) -> Path:
    """
    Convert a single .docx file to PDF using LibreOffice headless.
    Returns the path to the generated PDF.

    Raises a clear, specific error rather than a raw subprocess failure
    if LibreOffice isn't installed/found, or if conversion fails --
    this matters because a silent or cryptic failure here would be the
    last thing standing between "priced quotation" and "actual sendable
    file", and needs to fail loudly, not quietly.
    """
    docx_path = Path(docx_path)
    if not docx_path.exists():
        raise FileNotFoundError(f"{docx_path} does not exist -- nothing to convert.")

    output_dir = Path(output_dir) if output_dir else docx_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    soffice_path = find_soffice_executable()

    command = [
        soffice_path,
        "--headless",
        "--convert-to", "pdf",
        "--outdir", str(output_dir),
        str(docx_path),
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"LibreOffice conversion took longer than {timeout_seconds} seconds "
            f"and was stopped. This usually means a stuck LibreOffice process -- "
            f"check Task Manager / Activity Monitor for a hung 'soffice' process."
        ) from error

    expected_pdf_path = output_dir / (docx_path.stem + ".pdf")

    if result.returncode != 0 or not expected_pdf_path.exists():
        raise RuntimeError(
            f"LibreOffice conversion failed.\n"
            f"Command: {' '.join(command)}\n"
            f"Return code: {result.returncode}\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )

    return expected_pdf_path


if __name__ == "__main__":
    # Manual smoke test: convert the real quotation docx we already
    # generated and verified in the previous step.
    project_root = Path(__file__).resolve().parent.parent
    test_docx = project_root / "storage" / "generated_quotations" / "test_quotation_200.docx"

    if not test_docx.exists():
        print(f"'{test_docx}' not found. Run generate_docx.py first to create it.")
        sys.exit(1)

    print(f"Converting: {test_docx}")
    pdf_path = convert_docx_to_pdf(test_docx)
    print(f"SUCCESS. Generated PDF: {pdf_path}")
    print(f"PDF size: {pdf_path.stat().st_size:,} bytes")