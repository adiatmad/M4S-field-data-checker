"""Presentation-only Tetum translations for recognized M4S survey QA errors.

The English issue messages remain canonical for validation logic and compatibility.
Unknown messages, schema findings, warnings, and technical/system errors are left
unchanged until an explicitly reviewed translation is added.
"""
from __future__ import annotations

import re
import pandas as pd

# Only row-level survey-validation categories are eligible. Schema and technical
# failures are deliberately excluded.
SURVEY_ERROR_CATEGORIES = {
    "gps", "species", "logic", "numeric", "photo", "condition",
    "coverage_mismatch", "duplicate",
}

_EXACT_TRANSLATIONS = {
    "Missing GPS coordinates": "Koordenada GPS falta",
    "No quadrat photo attached": "Foto quadrante la anexa",
    "Missing seagrass general condition.": "Kondisaun jerál du'ut tasi falta.",
    "Presence of Seagrass = No but species were recorded": "Prezensa du'ut tasi = No, maibé rejistu ona espésie.",
    "Missing seagrass species: Presence of Seagrass = Yes but no species selected": "Espésie du'ut tasi falta: Prezensa du'ut tasi = Yes, maibé la hili espésie ida.",
    "End time is before or equal to start time": "Oras remata antes ka hanesan ho oras hahú",
    "Duplicate _uuid: the same submission may have been ingested twice.": "UUID repetidu: rejistu ida-ne'e bele tama dala rua.",
    "Key value duplicates another record; verify before changing either row.": "Valor xave hanesan ho rejistu seluk; verifika molok muda rejistu ida.",
}

def _translate_message(message: str) -> str | None:
    """Return a reviewed Tetum translation for a recognized survey QA template."""
    if message in _EXACT_TRANSLATIONS:
        return _EXACT_TRANSLATIONS[message]

    match = re.fullmatch(r"Mandatory field '(.+)' is missing or blank", message)
    if match:
        return f"Koluna obrigatóriu '{match.group(1)}' falta ka mamuk"

    match = re.fullmatch(r"Required column '(.+)' is missing", message)
    if match:
        return f"Koluna obrigatóriu '{match.group(1)}' falta"

    match = re.fullmatch(r"Required column is missing", message)
    if match:
        return "Koluna obrigatóriu falta"

    match = re.fullmatch(r"Nonblank value (.+) is not a valid number", message)
    if match:
        return f"Valor {match.group(1)} la'ós númeru válidu"

    match = re.fullmatch(r"(.+) marked present but no % cover recorded", message)
    if match:
        return f"Espésie {match.group(1)} marka hanesan prezente, maibé la rejista % kober"

    match = re.fullmatch(r"(.+) marked present but its percentage-cover column is missing from the export", message)
    if match:
        return f"Espésie {match.group(1)} marka hanesan prezente, maibé koluna persentajen kober la iha iha export"

    match = re.fullmatch(r"% cover recorded for (.+) but species not marked present", message)
    if match:
        return f"Rejista % kober ba {match.group(1)}, maibé la marka espésie hanesan prezente"

    match = re.fullmatch(r"(.+) % cover (.+) outside 0-100 range", message)
    if match:
        return f"% kober ba {match.group(1)} mak {match.group(2)}, liu husi limite 0–100"

    match = re.fullmatch(r"(.+) = (.+), outside 0-100 range", message)
    if match:
        return f"{match.group(1)} = {match.group(2)}, liu husi limite 0–100"

    match = re.fullmatch(r"Value (.+) is not a valid (number|integer|date|boolean)", message)
    if match:
        return f"Valor {match.group(1)} la'ós {match.group(2)} válidu"

    match = re.fullmatch(r"Value (.+) is not in the allowed-value list\.", message)
    if match:
        return f"Valor {match.group(1)} la tama iha lista valor ne'ebé permite."

    match = re.fullmatch(r"Numeric value (.+) is outside the configured range\.", message)
    if match:
        return f"Valor numériku {match.group(1)} liu husi limite ne'ebé define."

    match = re.fullmatch(r"Individual species percentages sum to (.+)% but Epicover Percentage is (.+)% \(difference: (.+)%; allowed tolerance: (.+) percentage points\)", message)
    if match:
        return (f"Totál persentajen espésie ida-idak mak {match.group(1)}%, maibé Epicover Percentage mak "
                f"{match.group(2)}% (diferensa: {match.group(3)}%; toleránsia ne'ebé permite: {match.group(4)} pontu persentajen)")

    # Deliberately do not guess a translation for unreviewed message patterns.
    return None


def format_qa_error_message(message, category, severity):
    """Format recognized survey QA errors as Tetum (exact English original)."""
    if str(severity).casefold() != "error" or category not in SURVEY_ERROR_CATEGORIES:
        return message
    if not isinstance(message, str):
        return message
    tetum = _translate_message(message)
    return f"{tetum} ({message})" if tetum else message


def localize_qa_issue_messages(issues: pd.DataFrame) -> pd.DataFrame:
    """Return a presentation copy; never mutate canonical issues or validation logic."""
    result = issues.copy()
    if not {"message", "category", "severity"}.issubset(result.columns):
        return result
    result["message"] = [
        format_qa_error_message(message, category, severity)
        for message, category, severity in zip(result["message"], result["category"], result["severity"])
    ]
    return result
