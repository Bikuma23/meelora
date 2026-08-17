"""Generic Document Service — immutable source-document store on Emergent Object
Storage. Reusable across ACCOUNTING (AR invoices, reminders) and future modules
(AP invoices, PO, bank vouchers, fixed assets, imports).

Design guarantees:
  * The binary lives in private Object Storage; MongoDB `source_documents` keeps
    ONLY metadata + storage reference + a SHA-256 content hash.
  * Immutable: a stored document is never overwritten. A new version produces a
    NEW object (new uuid storage key) + a NEW metadata row with an incremented
    version. Documents linked to a posted transaction are permanently frozen.
  * No public/permanent URL: retrieval always goes through the backend after a
    workspace + company + ACCOUNTING access check (enforced at the route layer).
  * Bidirectional traceability: each document carries (source_type, source_id)
    and, once the transaction is posted, its journal_entry_id. The journal entry
    stores source_document_id in return.
"""
import hashlib
import os
import uuid
import asyncio
from datetime import datetime, timezone

import requests
from fastapi import HTTPException

APP_NAME = "meelora"
_STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
_STORAGE_URL = _STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
_EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")

_storage_key = None


def _now():
    return datetime.now(timezone.utc).isoformat()


def init_storage(force: bool = False):
    global _storage_key
    if _storage_key and not force:
        return _storage_key
    resp = requests.post(f"{_STORAGE_URL}/init", json={"emergent_key": _EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def _put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = requests.put(f"{_STORAGE_URL}/objects/{path}",
                        headers={"X-Storage-Key": key, "Content-Type": content_type},
                        data=data, timeout=120)
    if resp.status_code == 404:
        init_storage(force=True)
        resp = requests.put(f"{_STORAGE_URL}/objects/{path}",
                            headers={"X-Storage-Key": init_storage(), "Content-Type": content_type},
                            data=data, timeout=120)
    resp.raise_for_status()
    return resp.json()


def _get_object(path: str):
    key = init_storage()
    resp = requests.get(f"{_STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    if resp.status_code == 404:
        init_storage(force=True)
        resp = requests.get(f"{_STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": init_storage()}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


def public_document(d):
    return {"id": d.get("_id"), "source_type": d.get("source_type"), "source_id": d.get("source_id"),
            "kind": d.get("kind"), "version": d.get("version"), "filename": d.get("filename"),
            "mime_type": d.get("mime_type"), "size": d.get("size"), "sha256": d.get("sha256"),
            "journal_entry_id": d.get("journal_entry_id"), "generated_at": d.get("generated_at"),
            "generated_by": d.get("generated_by"), "frozen": bool(d.get("frozen"))}


async def store_document(db, workspace_id, company_id, user, *, source_type, source_id,
                         data: bytes, filename, mime_type="application/pdf", kind="invoice", meta=None):
    """Upload an immutable source document. Returns public metadata. Always creates
    a NEW object + a NEW version; never overwrites a prior document."""
    prior = await db.source_documents.count_documents(
        {"workspace_id": workspace_id, "company_id": company_id, "source_type": source_type, "source_id": source_id})
    version = prior + 1
    doc_id = f"doc_{uuid.uuid4().hex}"
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "pdf").lower()
    storage_path = f"{APP_NAME}/documents/{workspace_id}/{company_id}/{source_type}/{source_id}/{uuid.uuid4().hex}.{ext}"
    sha256 = hashlib.sha256(data).hexdigest()
    try:
        result = await asyncio.to_thread(_put_object, storage_path, data, mime_type)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stockage du document indisponible : {e}")
    doc = {"_id": doc_id, "workspace_id": workspace_id, "company_id": company_id,
           "source_type": source_type, "source_id": source_id, "kind": kind, "version": version,
           "storage_path": result.get("path", storage_path), "filename": filename, "mime_type": mime_type,
           "size": result.get("size", len(data)), "sha256": sha256, "etag": result.get("etag"),
           "journal_entry_id": None, "frozen": False, "meta": meta or {},
           "generated_at": _now(), "generated_by": user.get("id"), "generated_by_email": user.get("email"),
           "is_deleted": False, "created_at": _now()}
    await db.source_documents.insert_one(doc)
    return public_document(doc)


async def get_document(db, workspace_id, company_id, doc_id):
    d = await db.source_documents.find_one(
        {"_id": doc_id, "workspace_id": workspace_id, "company_id": company_id, "is_deleted": {"$ne": True}})
    if not d:
        raise HTTPException(status_code=404, detail="Document introuvable")
    return d


async def list_documents(db, workspace_id, company_id, *, source_type=None, source_id=None):
    q = {"workspace_id": workspace_id, "company_id": company_id, "is_deleted": {"$ne": True}}
    if source_type:
        q["source_type"] = source_type
    if source_id:
        q["source_id"] = source_id
    docs = await db.source_documents.find(q).sort("version", -1).to_list(500)
    return [public_document(d) for d in docs]


async def latest_document(db, workspace_id, company_id, source_type, source_id):
    docs = await list_documents(db, workspace_id, company_id, source_type=source_type, source_id=source_id)
    return docs[0] if docs else None


async def download_document(db, workspace_id, company_id, doc_id):
    d = await get_document(db, workspace_id, company_id, doc_id)
    try:
        data, ct = await asyncio.to_thread(_get_object, d["storage_path"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Récupération du document impossible : {e}")
    if hashlib.sha256(data).hexdigest() != d.get("sha256"):
        raise HTTPException(status_code=409, detail="Intégrité du document compromise (hash non concordant).")
    return data, d.get("mime_type") or ct, d.get("filename")


async def company_branding_assets(db, workspace_id, company_id, company=None):
    """Return (logo_bytes|None, accent_hex|None) for official document rendering.
    Reuses the canonical company logo from Object Storage — no per-module upload."""
    if company is None:
        company = await db.companies.find_one(
            {"workspace_id": workspace_id, "$or": [{"id": company_id}, {"_id": company_id}]}) or {}
    branding = (company or {}).get("branding") or {}
    accent = branding.get("accent_color")
    logo_bytes = None
    did = branding.get("logo_document_id")
    if did:
        try:
            data, _mime, _fn = await download_document(db, workspace_id, company_id, did)
            logo_bytes = data
        except Exception:
            logo_bytes = None
    return logo_bytes, accent




async def link_journal(db, workspace_id, company_id, doc_id, journal_entry_id):
    """Freeze the document to its posted journal entry (bidirectional link)."""
    await db.source_documents.update_one(
        {"_id": doc_id, "workspace_id": workspace_id, "company_id": company_id},
        {"$set": {"journal_entry_id": journal_entry_id, "frozen": True, "updated_at": _now()}})
    await db.journal_entries.update_one(
        {"_id": journal_entry_id, "workspace_id": workspace_id, "company_id": company_id},
        {"$set": {"source_document_id": doc_id, "updated_at": _now()}})
