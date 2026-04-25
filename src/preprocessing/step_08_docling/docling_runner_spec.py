from __future__ import annotations

# Spec-variant of docling_runner.py used by run_docling_spec.py on the
# docling_spec_changes branch. Differs from the main runner in build_docling_converter():
#   - TableFormerMode.ACCURATE set explicitly (guards against future Docling default shifts)
#   - TableStructureOptions.do_cell_matching = True (aligns PDF text with TableFormer grid)
#   - do_picture_description = True with IBM Granite Vision 3.3-2b
#     (Phi-3.5-vision was tried first but Docling's PictureDescriptionVlmModel
#     hardcodes from_pretrained without trust_remote_code=True, which Phi requires.
#     Granite Vision is one of Docling's officially listed example VLMs and works
#     with the standard loader.)
#   - Heron layout model selected when the installed Docling version exposes it; otherwise
#     we log a warning and fall through to whatever Docling picks as default.
# Otherwise behaviour is identical to the main runner — markdown-only persistence,
# sequential processing, no docling_document JSONB.

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional


logger = logging.getLogger("docling")


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


def _try_heron_layout_options() -> Optional[Any]:
    """Return a LayoutOptions configured for Heron, or None if unavailable.

    Heron's exposure has shifted across Docling minor versions; rather than pin a single
    import path, try the known locations and bail out gracefully on any ImportError /
    AttributeError so the converter can still be built with the default layout model.
    """
    try:
        from docling.datamodel.pipeline_options import LayoutOptions  # type: ignore
        from docling.datamodel.layout_model_specs import DOCLING_LAYOUT_HERON  # type: ignore
        return LayoutOptions(model_spec=DOCLING_LAYOUT_HERON)
    except Exception as exc:  # noqa: BLE001 — defensive across Docling versions
        logger.warning(
            "Heron layout model not available in this Docling version (%s); "
            "falling back to default layout.", exc
        )
        return None


def _picture_description_options() -> Optional[Any]:
    """Return PictureDescriptionVlmOptions for Granite Vision 3.3-2b, or None if API missing."""
    try:
        from docling.datamodel.pipeline_options import PictureDescriptionVlmOptions  # type: ignore
        return PictureDescriptionVlmOptions(
            repo_id="ibm-granite/granite-vision-3.3-2b",
            prompt="Describe this image in detail. If it contains text, charts, or diagrams, transcribe the key information.",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "PictureDescriptionVlmOptions not available in this Docling version (%s); "
            "picture description disabled.", exc
        )
        return None


def build_docling_converter() -> Any:
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
        TableStructureOptions,
        TableFormerMode,
    )
    from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions

    accel = AcceleratorOptions(device=AcceleratorDevice.AUTO)

    table_options = TableStructureOptions(
        mode=TableFormerMode.ACCURATE,
        do_cell_matching=True,
    )

    pipeline_options = PdfPipelineOptions()
    pipeline_options.accelerator_options = accel
    pipeline_options.table_structure_options = table_options
    pipeline_options.do_table_structure = True
    pipeline_options.do_picture_description = True
    pipeline_options.generate_picture_images = True  # required so the VLM has pixels to describe

    pic_opts = _picture_description_options()
    if pic_opts is not None:
        pipeline_options.picture_description_options = pic_opts
    else:
        pipeline_options.do_picture_description = False

    layout_opts = _try_heron_layout_options()
    if layout_opts is not None:
        pipeline_options.layout_options = layout_opts
        logger.info("Layout model: Heron (explicit)")
    else:
        logger.info("Layout model: Docling default")

    logger.info(
        "Docling spec config — table_mode=ACCURATE, do_cell_matching=True, "
        "do_picture_description=%s",
        pipeline_options.do_picture_description,
    )

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
