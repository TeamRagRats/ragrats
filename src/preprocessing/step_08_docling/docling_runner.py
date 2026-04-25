from __future__ import annotations

# Wraps Docling's DocumentConverter. Builds a GPU-backed converter once and
# processes files one at a time, exporting Markdown only. The full DoclingDocument
# dict is no longer built or persisted — embedded image payloads pushed the
# serialised JSONB past Postgres' 256 MB per-value limit and nothing downstream
# consumed it.

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class FileResult:
    sha256: str
    source_path: str
    filename: str
    file_type: str
    file_size_bytes: int
    markdown: Optional[str] = None
    char_count: int = 0
    token_count: int = 0
    status: str = "pending"          # 'done' | 'error'
    error_message: Optional[str] = None
    duration_s: float = 0.0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


def build_docling_converter() -> Any:
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions

    accel = AcceleratorOptions(device=AcceleratorDevice.AUTO)
    pipeline_options = PdfPipelineOptions()
    pipeline_options.accelerator_options = accel

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )


def process_single_file(task, converter) -> FileResult:
    """Convert a single file through Docling. `task` is a QueueItem."""
    path = task.container_path
    size_bytes = path.stat().st_size if path.exists() else 0

    result = FileResult(
        sha256=task.sha256,
        source_path=str(task.container_path),
        filename=path.name,
        file_type=task.file_type,
        file_size_bytes=size_bytes,
    )
    result.started_at = datetime.now(timezone.utc)
    t0 = time.monotonic()

    try:
        if not path.exists():
            raise FileNotFoundError(f"Input missing: {path}")

        doc_result = converter.convert(str(path))
        md = doc_result.document.export_to_markdown()
        result.markdown = md
        result.char_count = len(md)
        result.token_count = len(md) // 4  # rough estimate, same as old pipeline

        if md.strip():
            result.status = "done"
        else:
            result.status = "error"
            result.error_message = "Empty markdown output"
    except Exception as exc:
        result.status = "error"
        result.error_message = f"{type(exc).__name__}: {exc}"

    result.duration_s = round(time.monotonic() - t0, 2)
    result.finished_at = datetime.now(timezone.utc)
    return result
