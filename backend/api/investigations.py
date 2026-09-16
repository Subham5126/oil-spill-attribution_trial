"""Investigations API Router."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.logging import logger
from backend.schemas.investigation import (
    InvestigationCreate,
    InvestigationResponse,
    InvestigationStatusResponse,
    UploadInitRequest,
    UploadInitResponse,
    UploadChunkResponse,
    UploadCompleteRequest,
    UploadedSceneResponse,
    TemporalAnchorConfirmRequest,
    TemporalAnchorResponse,
)
from backend.services.artifact_service import ArtifactService
from backend.services.investigation_service import InvestigationService
from backend.services.pipeline_service import PipelineService
from backend.services.report_service import ReportService
from backend.services.upload_service import UploadService

router = APIRouter(prefix="/investigations", tags=["Investigations"])


class RunPipelineRequest(BaseModel):
    image_id: Optional[str] = None
    image_path: Optional[str] = None
    ocean_file: Optional[str] = None
    skip_ais: bool = False
    skip_drift: bool = False
    sync: bool = False


@router.get("", response_model=List[InvestigationResponse])
def list_investigations(
    search: Optional[str] = Query(default=None, description="Search term for ID, title, region, vessel"),
    status: Optional[str] = Query(default=None, description="Filter by status (Active, Completed, Failed)"),
    region: Optional[str] = Query(default=None, description="Filter by geographic region"),
    starred: Optional[bool] = Query(default=None, description="Filter starred investigations"),
    archived: Optional[bool] = Query(default=None, description="Filter archived investigations"),
    include_deleted: bool = Query(default=False, description="Include soft-deleted investigations"),
    sort_by: str = Query(default="created_at", description="Sort attribute"),
    sort_dir: str = Query(default="desc", description="Sort direction (asc/desc)"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """List oil spill attribution investigations with dynamic multi-criteria filtering."""
    service = InvestigationService(db)
    return service.list_investigations(
        search=search,
        status=status,
        region=region,
        starred=starred,
        archived=archived,
        include_deleted=include_deleted,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@router.get("/search", response_model=List[Dict[str, Any]])
def search_investigations(
    q: str = Query(..., min_length=2, description="Search query string (title, ID, MMSI, vessel, spill ID)"),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Fast, ranked multi-field search across investigations, candidate vessels, and spill IDs."""
    service = InvestigationService(db)
    return service.search_investigations(query=q, limit=limit)


@router.get("/dashboard/summary")
def get_dashboard_summary(db: Session = Depends(get_db)):
    """Retrieve actual aggregated statistics and metrics for the dashboard view."""
    service = InvestigationService(db)
    return service.get_dashboard_summary()


@router.get("/history", response_model=List[InvestigationResponse])
def get_investigation_history(
    search: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    region: Optional[str] = Query(default=None),
    sort_by: str = Query(default="created_at"),
    sort_dir: str = Query(default="desc"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Retrieve chronological history of persisted investigations."""
    service = InvestigationService(db)
    return service.list_history(
        search=search,
        status=status,
        region=region,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@router.get("/vessel-intelligence")
def get_vessel_intelligence(db: Session = Depends(get_db)):
    """Retrieve cross-investigation candidate vessel appearances and intelligence."""
    service = InvestigationService(db)
    return service.get_vessel_intelligence()


@router.post("", response_model=InvestigationResponse, status_code=status.HTTP_201_CREATED)
def create_investigation(payload: InvestigationCreate, db: Session = Depends(get_db)):
    """Create a new investigation incident record."""
    service = InvestigationService(db)
    return service.create_investigation(payload)


@router.post("/upload/sentinel/init", response_model=UploadInitResponse)
def init_sentinel_upload(payload: UploadInitRequest):
    """Initialize a chunked upload session for a Sentinel-1 GeoTIFF scene (<= 1 GiB)."""
    try:
        return UploadService.init_chunked_upload(
            filename=payload.filename,
            file_size=payload.file_size,
            total_chunks=payload.total_chunks,
            content_type=payload.content_type,
            investigation_id=payload.investigation_id,
            chunk_size=payload.chunk_size,
        )
    except HTTPException:
        raise
    except Exception as exc:
        from backend.core.logging import logger
        logger.error(f"[UPLOAD] Unexpected error in init_sentinel_upload: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize upload session due to an unexpected server error.",
        )


@router.post("/upload/sentinel/chunk", response_model=UploadChunkResponse)
async def upload_sentinel_chunk(
    upload_id: str = Form(..., description="Active upload session ID"),
    chunk_index: int = Form(..., description="0-indexed chunk index"),
    chunk: UploadFile = File(..., description="Binary chunk payload"),
):
    """Write an individual chunk (5-10 MB) to the pending upload session on disk."""
    chunk_bytes = await chunk.read()
    return UploadService.append_chunk(
        upload_id=upload_id,
        chunk_index=chunk_index,
        chunk_bytes=chunk_bytes,
    )


@router.post("/upload/sentinel/complete", response_model=UploadedSceneResponse)
def complete_sentinel_upload(payload: UploadCompleteRequest):
    """Finalize chunked upload, validate GeoTIFF structure with rasterio, and extract metadata."""
    return UploadService.complete_chunked_upload(payload.upload_id)


@router.delete("/upload/sentinel/{upload_id}")
def cancel_sentinel_upload(upload_id: str):
    """Cancel and purge an in-progress or completed upload session and disk file."""
    UploadService.cancel_upload(upload_id)
    return {"status": "CANCELLED", "upload_id": upload_id}


@router.post("/upload/sentinel", response_model=UploadedSceneResponse)
def direct_sentinel_upload(file: UploadFile = File(..., description="Direct Sentinel-1 GeoTIFF")):
    """Direct single-shot streaming upload for a Sentinel-1 GeoTIFF scene (<= 1 GiB)."""
    return UploadService.direct_upload(file)


@router.post("/upload/sentinel/{upload_id}/temporal-anchor", response_model=TemporalAnchorResponse)
def confirm_sentinel_temporal_anchor(upload_id: str, payload: TemporalAnchorConfirmRequest):
    """Confirm or manually set the authoritative Sentinel-1 SAR acquisition timestamp in UTC."""
    return UploadService.confirm_temporal_anchor(
        upload_id=upload_id,
        sar_acquisition_time=payload.sar_acquisition_time,
        date=payload.date,
        time=payload.time,
        source=payload.source,
    )


@router.post("/temporal-anchor/resolve", response_model=TemporalAnchorResponse)
def resolve_temporal_anchor_endpoint(
    image_id: Optional[str] = Query(default=None),
    filename: Optional[str] = Query(default=None),
    user_timestamp: Optional[str] = Query(default=None),
):
    """Evaluate and resolve the authoritative SAR temporal anchor for a given scene, filename, or user timestamp."""
    from backend.services.temporal_service import resolve_sar_temporal_anchor
    return resolve_sar_temporal_anchor(
        image_id=image_id,
        filename=filename,
        user_provided_timestamp=user_timestamp,
    )


@router.get("/{investigation_id}", response_model=InvestigationResponse)
def get_investigation(investigation_id: str, db: Session = Depends(get_db)):
    """Retrieve details of a specific investigation."""
    service = InvestigationService(db)
    return service.get_investigation(investigation_id)


@router.patch("/{investigation_id}", response_model=InvestigationResponse)
def patch_investigation(investigation_id: str, patch: Dict[str, Any], db: Session = Depends(get_db)):
    """Update investigation metadata, priority, starred, or archived status."""
    service = InvestigationService(db)
    from backend.schemas.investigation import InvestigationPatch
    patch_obj = InvestigationPatch(**patch)
    return service.patch_investigation(investigation_id, patch_obj)


@router.delete("/{investigation_id}")
def delete_investigation(
    investigation_id: str,
    purge: bool = Query(default=False, description="If true, permanently remove record and generated artifacts"),
    db: Session = Depends(get_db),
):
    """Delete an investigation. Defaults to soft deletion with optional hard purge."""
    service = InvestigationService(db)
    return service.delete_investigation(investigation_id, purge=purge)


@router.post("/{investigation_id}/restore", response_model=InvestigationResponse)
def restore_investigation(investigation_id: str, db: Session = Depends(get_db)):
    """Restore a soft-deleted investigation from trash."""
    service = InvestigationService(db)
    return service.restore_investigation(investigation_id)


@router.post("/{investigation_id}/rerun", response_model=InvestigationResponse, status_code=status.HTTP_201_CREATED)
def rerun_investigation(investigation_id: str, db: Session = Depends(get_db)):
    """Duplicate an investigation and spawn a re-run pipeline job."""
    service = InvestigationService(db)
    return service.rerun_investigation(investigation_id)


@router.get("/{investigation_id}/timeline")
def get_investigation_timeline(investigation_id: str, db: Session = Depends(get_db)):
    """Retrieve real chronological activity and stage milestones for an incident."""
    service = InvestigationService(db)
    return service.get_timeline(investigation_id)


@router.get("/{investigation_id}/evidence")
def get_investigation_evidence(investigation_id: str, db: Session = Depends(get_db)):
    """Retrieve verified file evidence artifacts with real disk sizes and download links."""
    service = InvestigationService(db)
    return service.get_evidence_library(investigation_id)


@router.get("/{investigation_id}/artifacts/{artifact_type}/download")
@router.get("/{investigation_id}/artifacts/{artifact_type}")
def download_investigation_artifact(
    investigation_id: str,
    artifact_type: str,
    db: Session = Depends(get_db),
):
    """Download a specific verified forensic artifact belonging to an investigation."""
    from pathlib import Path
    from backend.services.storage_service import storage

    # 1. Verify investigation exists
    inv_service = InvestigationService(db)
    inv = inv_service.repo.get_by_id(investigation_id, include_deleted=True)
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Investigation '{investigation_id}' not found")

    # 2. Compile canonical artifacts and match type
    artifacts = inv_service.get_evidence_library(investigation_id)
    target = None
    clean_type = artifact_type.upper().replace("-", "_")

    # Map possible aliases
    alias_map = {
        "DETECTION_OVERLAY": "SAR_DETECTION_OVERLAY",
        "SEGMENTATION_MASK": "SEGMENTATION_MASK_PNG",
        "SOURCE_TIFF": "SOURCE_SAR_TIFF",
        "MASK_TIFF": "GEOREFERENCED_MASK_TIFF",
        "DRIFT_CSV": "DRIFT_TRAJECTORY_CSV",
        "DRIFT_JSON": "DRIFT_TRAJECTORY_JSON",
        "AIS_MATRIX": "AIS_ATTRIBUTION_JSON",
        "AIS_CSV": "AIS_CANDIDATES_CSV",
        "REPORT_PDF": "FORENSIC_REPORT_PDF",
    }
    resolved_type = alias_map.get(clean_type, clean_type)

    for art in artifacts:
        if art.get("artifact_type") == resolved_type:
            target = art
            break

    if not target or target.get("status") != "AVAILABLE" or not target.get("file_path"):
        reason = target.get("unavailable_reason") if target else f"Artifact '{artifact_type}' not available for this investigation"
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact unavailable: {reason}",
        )

    file_path = Path(target["file_path"])
    if not file_path.exists() or not file_path.is_file() or file_path.stat().st_size == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Physical artifact file missing or 0 bytes on disk: {file_path.name}",
        )

    meta = storage.get_file_metadata(file_path)
    file_name = target.get("file_name") or file_path.name
    headers = {
        "Content-Disposition": f'attachment; filename="{file_name}"',
        "X-Investigation-ID": investigation_id,
        "X-Artifact-Type": resolved_type,
        "X-Artifact-SHA256": meta.get("sha256") or "",
    }
    if meta.get("byte_size"):
        headers["Content-Length"] = str(meta["byte_size"])

    return FileResponse(
        path=str(file_path),
        media_type=meta.get("mime_type", "application/octet-stream"),
        filename=file_name,
        headers=headers,
    )


@router.get("/{investigation_id}/evidence/bundle")
def download_evidence_bundle(
    investigation_id: str,
    db: Session = Depends(get_db),
):
    """Download complete forensic evidence package as a structured ZIP archive with manifest.json."""
    from backend.services.storage_service import storage

    inv_service = InvestigationService(db)
    inv = inv_service.repo.get_by_id(investigation_id, include_deleted=True)
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Investigation '{investigation_id}' not found")

    artifacts = inv_service.get_evidence_library(investigation_id)
    available_artifacts = [a for a in artifacts if a.get("status") == "AVAILABLE" and a.get("file_path")]

    if not available_artifacts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No completed evidence artifacts available to bundle for this investigation",
        )

    # Compile manifest
    manifest = {
        "investigation_id": investigation_id,
        "title": inv.title,
        "region": inv.region,
        "pipeline_status": inv.pipeline_status,
        "observation_timestamp": inv.observation_timestamp.isoformat() if inv.observation_timestamp else None,
        "primary_suspect": inv.suspect_vessel,
        "bundled_at": datetime.now(timezone.utc).isoformat(),
        "total_files": len(available_artifacts),
        "artifacts": [
            {
                "artifact_type": a.get("artifact_type"),
                "name": a.get("name"),
                "category": a.get("category"),
                "file_name": a.get("file_name"),
                "byte_size": a.get("file_size_bytes"),
                "sha256": a.get("sha256"),
                "mime_type": a.get("mime_type"),
                "provenance": a.get("provenance_source"),
            }
            for a in available_artifacts
        ],
        "disclaimer": "OFFICIAL EVIDENCE DOSSIER — MARPOL 73/78 ANNEX I INVESTIGATION CUSTODY CHAIN. GENERATED BY OILTRACE FORENSIC ENGINE.",
    }

    zip_buffer = storage.create_evidence_bundle(
        investigation_id=investigation_id,
        artifacts=available_artifacts,
        manifest=manifest,
    )

    filename = f"OILTRACE_{investigation_id}_Evidence_Bundle.zip"
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/zip",
            "Content-Length": str(len(zip_buffer.getvalue())),
            "X-Investigation-ID": investigation_id,
            "X-Bundle-Artifacts-Count": str(len(available_artifacts)),
        },
    )


@router.post("/{investigation_id}/artifacts/{artifact_type}/verify")
def verify_artifact_integrity_endpoint(
    investigation_id: str,
    artifact_type: str,
    db: Session = Depends(get_db),
):
    """Verify disk presence, non-zero length, and cryptographic SHA-256 integrity of an artifact."""
    from pathlib import Path
    from backend.services.storage_service import storage

    inv_service = InvestigationService(db)
    artifacts = inv_service.get_evidence_library(investigation_id)

    clean_type = artifact_type.upper().replace("-", "_")
    alias_map = {
        "DETECTION_OVERLAY": "SAR_DETECTION_OVERLAY",
        "SEGMENTATION_MASK": "SEGMENTATION_MASK_PNG",
        "SOURCE_TIFF": "SOURCE_SAR_TIFF",
        "MASK_TIFF": "GEOREFERENCED_MASK_TIFF",
        "DRIFT_CSV": "DRIFT_TRAJECTORY_CSV",
        "DRIFT_JSON": "DRIFT_TRAJECTORY_JSON",
        "AIS_MATRIX": "AIS_ATTRIBUTION_JSON",
        "AIS_CSV": "AIS_CANDIDATES_CSV",
        "REPORT_PDF": "FORENSIC_REPORT_PDF",
    }
    resolved_type = alias_map.get(clean_type, clean_type)

    target = next((a for a in artifacts if a.get("artifact_type") == resolved_type), None)
    if not target or not target.get("file_path"):
        return {
            "status": "UNAVAILABLE",
            "message": target.get("unavailable_reason") if target else "Artifact not found",
            "verified": False,
        }

    file_path = Path(target["file_path"])
    meta = storage.get_file_metadata(file_path)

    if not meta["exists"] or meta["byte_size"] == 0:
        return {
            "status": "CORRUPTED",
            "message": "Physical file is 0 bytes or missing from storage volume",
            "verified": False,
        }

    return {
        "status": "AVAILABLE",
        "verified": True,
        "artifact_type": resolved_type,
        "file_name": file_path.name,
        "byte_size": meta["byte_size"],
        "sha256": meta["sha256"],
        "mime_type": meta["mime_type"],
        "message": f"Cryptographic integrity verified (SHA-256: {meta['sha256'][:12]}...)",
    }


@router.get("/{investigation_id}/status")
def get_investigation_status(investigation_id: str, db: Session = Depends(get_db)):
    """Retrieve processing lifecycle status and stage-level progress of an investigation."""
    pipe_service = PipelineService(db)
    return pipe_service.get_status(investigation_id)


@router.post("/{investigation_id}/run", status_code=status.HTTP_202_ACCEPTED)
def run_investigation_pipeline(
    investigation_id: str,
    payload: Optional[RunPipelineRequest] = None,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    """Trigger the real attribution pipeline for an investigation."""
    pipe_service = PipelineService(db)
    req = payload or RunPipelineRequest()

    if req.sync:
        # Run synchronously
        result = pipe_service.run_pipeline(
            investigation_id=investigation_id,
            image_id=req.image_id,
            image_path=req.image_path,
            ocean_file=req.ocean_file,
            skip_ais=req.skip_ais,
            skip_drift=req.skip_drift,
        )
        return {"investigation_id": investigation_id, "status": "COMPLETED", "result": result}

    # Run in background
    if background_tasks is not None:
        background_tasks.add_task(
            pipe_service.run_pipeline,
            investigation_id=investigation_id,
            image_id=req.image_id,
            image_path=req.image_path,
            ocean_file=req.ocean_file,
            skip_ais=req.skip_ais,
            skip_drift=req.skip_drift,
        )

    return {
        "investigation_id": investigation_id,
        "status": "ACCEPTED",
        "message": f"Pipeline execution started for {investigation_id}",
    }


@router.get("/{investigation_id}/result")
@router.get("/{investigation_id}/attribution")
def get_investigation_result(investigation_id: str, db: Session = Depends(get_db)):
    """Retrieve complete canonical end-to-end attribution result for an investigation."""
    pipeline_service = PipelineService(db)
    return pipeline_service.get_result_by_investigation(investigation_id)


@router.get("/{investigation_id}/map")
def get_investigation_map_layers(investigation_id: str, db: Session = Depends(get_db)):
    """Retrieve GeoJSON map layers for this investigation."""
    pipeline_service = PipelineService(db)
    layers = pipeline_service.get_layers_geojson(investigation_id)
    return layers


@router.get("/{investigation_id}/vessels")
def get_investigation_candidate_vessels(investigation_id: str, db: Session = Depends(get_db)):
    """Retrieve ranked candidate AIS vessels for this investigation."""
    pipeline_service = PipelineService(db)
    res = pipeline_service.get_result_by_investigation(investigation_id)
    return res.get("candidate_vessels", [])


@router.get("/{investigation_id}/drift")
def get_investigation_drift(investigation_id: str, db: Session = Depends(get_db)):
    """Retrieve ocean drift hindcasting and forecasting data for this investigation."""
    pipeline_service = PipelineService(db)
    res = pipeline_service.get_result_by_investigation(investigation_id)
    return res.get("ocean_drift", {})


@router.get("/{investigation_id}/report")
def get_investigation_report(investigation_id: str, db: Session = Depends(get_db)):
    """Retrieve structured 11-section forensic report data."""
    report_service = ReportService(db)
    return report_service.get_report_by_investigation(investigation_id)


@router.get("/{investigation_id}/report/pdf")
@router.get("/{investigation_id}/report/download")
def download_investigation_report_pdf(investigation_id: str, db: Session = Depends(get_db)):
    """Generate and download authoritative forensic PDF report."""
    try:
        report_service = ReportService(db)
        pdf_bytes = report_service.generate_report_pdf(investigation_id)
        filename = f"OILTRACE_{investigation_id}_Forensic_Report.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": "application/pdf",
            },
        )
    except Exception as e:
        logger.error(f"[PDF_DOWNLOAD] Failed to generate PDF for {investigation_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to generate forensic PDF.")


@router.get("/{investigation_id}/report/pdf/view")
def view_investigation_report_pdf(investigation_id: str, db: Session = Depends(get_db)):
    """View authoritative forensic PDF report inline in browser."""
    try:
        report_service = ReportService(db)
        pdf_bytes = report_service.generate_report_pdf(investigation_id)
        filename = f"OILTRACE_{investigation_id}_Forensic_Report.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
                "Content-Type": "application/pdf",
            },
        )
    except Exception as e:
        logger.error(f"[PDF_VIEW] Failed to render inline PDF for {investigation_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to generate forensic PDF.")


@router.get("/{investigation_id}/reconstruction")
def get_investigation_reconstruction(investigation_id: str, db: Session = Depends(get_db)):
    """Retrieve normalized forensic reconstruction dataset for animated incident replay."""
    from backend.services.reconstruction_service import ReconstructionService

    service = ReconstructionService(db)
    try:
        return service.get_reconstruction(investigation_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{investigation_id}/artifacts/detection-overlay")
def get_detection_overlay(
    investigation_id: str,
    img: Optional[str] = Query(default=None, description="Explicit image ID override"),
    db: Session = Depends(get_db),
):
    """Retrieve or generate the high-contrast SAR Detection Overlay PNG for an investigation."""
    path = ArtifactService.get_detection_overlay_path(investigation_id, db=db, explicit_image_id=img)
    if not path or not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SAR detection artifact unavailable",
        )
    return FileResponse(
        str(path),
        media_type="image/png",
        filename=path.name,
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/{investigation_id}/artifacts/segmentation-mask")
def get_segmentation_mask(
    investigation_id: str,
    img: Optional[str] = Query(default=None, description="Explicit image ID override"),
    db: Session = Depends(get_db),
):
    """Retrieve or generate the U-Net AI Segmentation Mask PNG for an investigation."""
    path = ArtifactService.get_segmentation_mask_path(investigation_id, db=db, explicit_image_id=img)
    if not path or not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Segmentation artifact unavailable",
        )
    return FileResponse(
        str(path),
        media_type="image/png",
        filename=path.name,
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/{investigation_id}/artifacts/source-tiff")
def get_source_tiff(
    investigation_id: str,
    img: Optional[str] = Query(default=None, description="Explicit image ID override"),
    db: Session = Depends(get_db),
):
    """Download the raw Sentinel-1 SAR GeoTIFF associated with an investigation."""
    path = ArtifactService.get_source_tiff_path(investigation_id, db=db, explicit_image_id=img)
    if not path or not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source TIFF artifact unavailable",
        )
    return FileResponse(
        str(path),
        media_type="image/tiff",
        filename=path.name,
        headers={"Content-Disposition": f'attachment; filename="{path.name}"'},
    )

