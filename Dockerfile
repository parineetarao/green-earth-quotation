# Render's native (non-Docker) Python runtime has no way to apt-get
# system packages, but documents/convert_to_pdf.py shells out to a real
# `soffice` (LibreOffice) binary to turn the generated .docx quotation
# into a PDF -- there's no pure-Python substitute that preserves the real
# Word template's layout (see that file's docstring). A Dockerfile is the
# only Render deployment path that lets us install LibreOffice alongside
# the Python app.
FROM python:3.11-slim

# libreoffice-writer (not the full `libreoffice` meta-package) is enough
# to convert .docx -> .pdf and keeps the image smaller/faster to build.
# fonts-liberation ships metric-compatible fallbacks for common Word
# fonts so the PDF layout doesn't shift as much when the exact font
# isn't installed on this Linux box.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libreoffice-writer \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render sets $PORT at runtime; must bind 0.0.0.0 to be reachable.
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
