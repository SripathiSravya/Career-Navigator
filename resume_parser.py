import re, io
from pypdf import PdfReader
from database import ALIASES
def extract_text(data):
    if not data.startswith(b"%PDF"): raise ValueError("The uploaded file is not a valid PDF.")
    try:
        text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
    except Exception:
        raise ValueError("The PDF could not be read. It may be corrupted or password-protected.")
    if len(text.split()) < 20: raise ValueError("No readable text found in the PDF (it may be a scanned image). Please upload a text-based PDF.")
    return text
def _has(term, low): return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9+#])", low) is not None
def find_skills(text, vocab):
    low = text.lower(); found = {}
    for key, disp in vocab.items():
        if _has(key, low): found[key] = disp
    for alias, target in ALIASES.items():
        if target in vocab and _has(alias, low): found[target] = vocab[target]
    return sorted(found.values(), key=str.lower)
