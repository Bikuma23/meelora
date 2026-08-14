"""Source readers — transport/file concerns only (NO accounting business rules).

Extracts the Excel/CSV reading that was duplicated across the accounts /
trial_balance / journal parsers. Business interpretation belongs in adapters.
"""
import csv as _csv
import io
from typing import Callable

from fastapi import HTTPException


def _cell_str(v) -> str:
    """Stringify a cell WITHOUT losing leading zeros / punctuation for text values.
    Numeric cells render without a trailing .0 for whole numbers."""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _is_csv(content: bytes, file_name: str) -> bool:
    name = (file_name or "").lower()
    return name.endswith(".csv") or (not name.endswith((".xlsx", ".xls")) and b"PK" not in content[:4])


def read_tabular(content: bytes, file_name: str, normalizer: Callable):
    """Return (rows, header_fields).

    rows: list of {"_row": <1-based data row>, <normalized_field>: str}.
    header_fields: set of normalized field names present in the header.
    Raises 400 on an unreadable/empty file.
    """
    if _is_csv(content, file_name):
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("latin-1")
        reader = list(_csv.reader(io.StringIO(text)))
        if not reader:
            raise HTTPException(status_code=400, detail="Fichier vide")
        header_map = {i: normalizer(h) for i, h in enumerate(reader[0])}
        header_fields = {v for v in header_map.values() if v}
        rows = []
        for idx, raw in enumerate(reader[1:], start=2):
            if not any((c or "").strip() for c in raw):
                continue
            row = {"_row": idx}
            for i, field in header_map.items():
                if field and i < len(raw):
                    row[field] = (raw[i] or "").strip()
            rows.append(row)
        return rows, header_fields

    import openpyxl
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Fichier Excel illisible")
    ws = wb.active
    it = ws.iter_rows(values_only=True)
    try:
        header = next(it)
    except StopIteration:
        raise HTTPException(status_code=400, detail="Fichier vide")
    header_map = {i: normalizer(h) for i, h in enumerate(header)}
    header_fields = {v for v in header_map.values() if v}
    rows = []
    for idx, raw in enumerate(it, start=2):
        if raw is None or not any(c is not None and str(c).strip() for c in raw):
            continue
        row = {"_row": idx}
        for i, field in header_map.items():
            if field and i < len(raw):
                row[field] = _cell_str(raw[i])
        rows.append(row)
    return rows, header_fields
