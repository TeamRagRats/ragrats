from __future__ import annotations

# Writes attachment payloads to disk under attachment_root/voyage_key/.
# Deduplicates by SHA-256: identical content reuses the existing file; name collisions
# get a counter suffix. Returns a list of WrittenAttachment for DB insertion.
# Uses hash_attachment and classify_attachment; consumed by run_ingest.py.

import re
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from step_02_parse.parse_eml import AttachmentPart
from step_05_attachments.classify_attachment import is_docling_ready
from step_05_attachments.hash_attachment import sha256_hex

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str) -> str:
    cleaned = _UNSAFE.sub("_", name).strip("._") or "attachment.bin"
    return cleaned[:180]


@dataclass
class WrittenAttachment:
    file_name: str
    file_path: Path
    file_type: str | None
    size_bytes: int
    sha256: str
    docling_ready: bool


def extract_attachments(
    attachment_root: Path,
    voyage_key: str,
    email_id: UUID,
    parts: list[AttachmentPart],
    dry_run: bool = False,
) -> list[WrittenAttachment]:
    out: list[WrittenAttachment] = []
    target_dir = attachment_root / voyage_key
    if not dry_run and parts:
        target_dir.mkdir(parents=True, exist_ok=True)
    
    for part in parts:
        sha256 = sha256_hex(part.payload)
        base = safe_filename(part.file_name)
        
        final_name = base
        counter = 1
        
        while True:
            path = target_dir / final_name
            
            # 1. If path doesn't exist, we write it.
            if not path.exists():
                if not dry_run:
                    path.write_bytes(part.payload)
                break
                
            # 2. If it's a dry run, we just assume the name is fine 
            # (since we can't write/compare effectively).
            if dry_run:
                break
            
            # 3. Path exists. Check if it's the SAME content.
            # We read the existing file and compare hashes.
            try:
                existing_hash = sha256_hex(path.read_bytes())
                if existing_hash == sha256:
                    # Content is identical! Deduplicate: reuse the path.
                    break
            except Exception:
                # If we can't read it for some reason, treat as collision.
                pass
            
            # 4. Content is different, but name is the same. Collision!
            # Append a counter and try again.
            name_parts = base.rsplit(".", 1)
            if len(name_parts) == 2:
                final_name = f"{name_parts[0]}_{counter}.{name_parts[1]}"
            else:
                final_name = f"{base}_{counter}"
            counter += 1
            
        out.append(
            WrittenAttachment(
                file_name=final_name,
                file_path=path,
                file_type=part.mime_type,
                size_bytes=len(part.payload),
                sha256=sha256,
                docling_ready=is_docling_ready(part.mime_type, final_name),
            )
        )
    return out
