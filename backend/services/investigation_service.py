from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.exceptions import InvestigationNotFoundError
from backend.core.logging import logger
from backend.models.investigation import InvestigationModel
from backend.repositories.investigations import InvestigationRepository
from backend.schemas.investigation import (
    InvestigationCreate,
    InvestigationPatch,
    InvestigationResponse,
    InvestigationStatusResponse,
)
from backend.services.image_service import ImageService
from backend.services.confidence_scoring import resolve_confidence_level


class InvestigationService:
    """Service coordinating investigation lifecycle, query filtering, and telemetry."""

    def __init__(self, db: Optional[Session] = None):
        self.db = db
        self.repo = InvestigationRepository(db)

    def _to_dict(self, r: InvestigationModel) -> Dict[str, Any]:
        coord = None
        if r.centroid_lat is not None and r.centroid_lon is not None:
            coord = {
                "latitude": r.centroid_lat,
                "longitude": r.centroid_lon,
            }

        return {
            "id": r.investigation_id,
            "title": r.title,
            "status": r.status,
            "priority": r.priority,
            "region": r.region,
            "image_id": r.image_id,
            "coordinates": coord,
            "spill_area_km2": round(r.spill_area_km2 or 0.0, 4),
            "detection_time": r.observation_timestamp.isoformat() if r.observation_timestamp else None,
            "sar_acquisition_time": (
                r.sar_acquisition_time.isoformat()
                if getattr(r, "sar_acquisition_time", None)
                else (r.observation_timestamp.isoformat() if r.observation_timestamp else None)
            ),
            "sar_acquisition_time_source": getattr(r, "sar_acquisition_time_source", None),
            "sar_acquisition_time_verified": getattr(r, "sar_acquisition_time_verified", None),
            "suspect_vessel": r.suspect_vessel,
            "match_confidence": r.match_confidence,
            "evidence_nodes_count": r.evidence_nodes_count,
            "sar_epoch": r.sar_epoch or "N/A",
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "is_starred": bool(r.is_starred),
            "is_archived": bool(r.is_archived),
            "is_deleted": bool(r.is_deleted),
            "parent_investigation_id": r.parent_investigation_id,
            "artifacts": {
                "detection_overlay": f"/api/investigations/{r.investigation_id}/artifacts/detection-overlay",
                "segmentation_mask": f"/api/investigations/{r.investigation_id}/artifacts/segmentation-mask",
                "source_tiff": f"/api/investigations/{r.investigation_id}/artifacts/source-tiff",
            },
        }

    def list_investigations(
        self,
        search: Optional[str] = None,
        status: Optional[str] = None,
        region: Optional[str] = None,
        starred: Optional[bool] = None,
        archived: Optional[bool] = None,
        include_deleted: bool = False,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List active investigations with comprehensive multi-criteria filtering."""
        records = self.repo.list_all(
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
        return [self._to_dict(r) for r in records]

    def list_history(
        self,
        search: Optional[str] = None,
        status: Optional[str] = None,
        region: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List historical investigations with chronological search and date filtering."""
        records = self.repo.list_history(
            search=search,
            status=status,
            region=region,
            from_date=from_date,
            to_date=to_date,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )
        return [self._to_dict(r) for r in records]

    def search_investigations(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search investigations across title, ID, region, suspect vessel, candidate vessels (name, MMSI), and spill IDs.
        
        Ranks results strictly by user-specified priority:
        1. Exact investigation ID
        2. Exact incident title
        3. Starts-with title match
        4. Vessel name
        5. MMSI
        6. Spill ID
        7. Partial text match
        """
        if not query or len(query.strip()) < 2:
            return []

        q = query.strip()
        q_lower = q.lower()

        records = self.repo.list_all(include_deleted=False, limit=200)
        scored_matches: List[tuple[int, datetime, Dict[str, Any]]] = []

        for rec in records:
            inv_id = rec.investigation_id or ""
            title = rec.title or ""
            region = rec.region or ""
            suspect = rec.suspect_vessel or ""
            created = rec.created_at or datetime.min.replace(tzinfo=timezone.utc)

            match_score = 0
            match_type = "general"
            match_label = ""

            # Check candidate vessels & MMSI
            matched_vessel = None
            matched_mmsi = None
            if hasattr(rec, "attribution_results") and rec.attribution_results:
                for attr in rec.attribution_results:
                    v_name = attr.vessel_name or ""
                    mmsi_str = str(attr.mmsi) if attr.mmsi else ""
                    if q_lower in v_name.lower():
                        matched_vessel = v_name
                    if q in mmsi_str:
                        matched_mmsi = mmsi_str

            # Check spill IDs
            matched_spill = None
            if hasattr(rec, "spills") and rec.spills:
                for spill in rec.spills:
                    s_id = spill.spill_id or ""
                    if q_lower in s_id.lower():
                        matched_spill = s_id

            # Priority 1: Exact Investigation ID
            if q_lower == inv_id.lower():
                match_score = 100
                match_type = "id"
                match_label = f"Case ID: {inv_id}"
            # Priority 2: Exact Incident Title
            elif q_lower == title.lower():
                match_score = 90
                match_type = "title"
                match_label = "Exact Title Match"
            # Priority 3: Starts-with Title Match
            elif title.lower().startswith(q_lower):
                match_score = 80
                match_type = "title"
                match_label = "Title Match"
            # Priority 4: Vessel Name (exact or partial)
            elif (suspect and q_lower in suspect.lower()) or matched_vessel:
                vname = suspect if (suspect and q_lower in suspect.lower()) else matched_vessel
                match_score = 70
                match_type = "vessel"
                match_label = f"Vessel: {vname}"
            # Priority 5: MMSI
            elif matched_mmsi:
                match_score = 60
                match_type = "mmsi"
                match_label = f"MMSI: {matched_mmsi}"
            # Priority 6: Spill ID
            elif matched_spill:
                match_score = 50
                match_type = "spill_id"
                match_label = f"Spill: {matched_spill}"
            # Priority 7: Title contains keyword
            elif q_lower in title.lower():
                match_score = 40
                match_type = "title"
                match_label = "Title Keyword"
            # Priority 8: Investigation ID contains keyword
            elif q_lower in inv_id.lower():
                match_score = 35
                match_type = "id"
                match_label = f"Case ID: {inv_id}"
            # Priority 9: Region or general text match
            elif q_lower in region.lower():
                match_score = 30
                match_type = "general"
                match_label = f"Region: {region}"

            if match_score > 0:
                item = {
                    "id": inv_id,
                    "investigation_id": inv_id,
                    "title": title,
                    "region": region,
                    "status": rec.status,
                    "spill_area_km2": rec.spill_area_km2 or 0.0,
                    "suspect_vessel": suspect or None,
                    "match_type": match_type,
                    "match_label": match_label,
                    "created_at": rec.created_at.isoformat() if rec.created_at else None,
                }
                scored_matches.append((match_score, created, item))

        # Sort by score descending, then created_at descending
        scored_matches.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [match[2] for match in scored_matches[:limit]]

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Aggregate actual real-time metrics across all persisted investigations."""
        summary = self.repo.count_summary()
        recent_records = self.repo.list_all(limit=5, sort_by="created_at", sort_dir="desc")
        latest_completed = self.repo.list_all(status="completed", limit=1, sort_by="created_at", sort_dir="desc")

        # Calculate authoritative forensic readiness state
        if summary["total"] == 0:
            readiness_status = "STANDBY"
            readiness_detail = "Awaiting investigation"
        elif summary["running"] > 0:
            readiness_status = "PROCESSING"
            readiness_detail = "Investigation pipeline active"
        elif summary["failed"] > 0:
            readiness_status = "ATTENTION"
            readiness_detail = "Evidence requires review"
        elif summary["completed"] > 0:
            readiness_status = "READY"
            readiness_detail = "Evidence standards satisfied"
        else:
            readiness_status = "STANDBY"
            readiness_detail = "Awaiting investigation"

        return {
            "total_investigations": summary["total"],
            "completed_investigations": summary["completed"],
            "active_investigations": summary["active"],
            "running_investigations": summary["running"],
            "failed_investigations": summary["failed"],
            "total_spill_area_km2": summary["total_spill_area_km2"],
            "candidate_vessels_tracked": summary["candidate_vessels_count"],
            "forensic_readiness": {
                "status": readiness_status,
                "detail": readiness_detail,
            },
            "recent_investigations": [self._to_dict(r) for r in recent_records],
            "latest_completed_investigation": self._to_dict(latest_completed[0]) if latest_completed else None,
        }

    def get_investigation(self, investigation_id: str) -> Dict[str, Any]:
        """Fetch investigation by public identifier."""
        record = self.repo.get_by_id(investigation_id, include_deleted=True)
        if record:
            return self._to_dict(record)

        raise InvestigationNotFoundError(
            f"Investigation '{investigation_id}' not found",
            stage="INVESTIGATION_LOOKUP",
        )

    def create_investigation(self, payload: InvestigationCreate) -> Dict[str, Any]:
        import uuid
        now = datetime.now(timezone.utc)
        inv_id = f"INV-{now.strftime('%Y')}-{uuid.uuid4().hex[:6].upper()}"

        from backend.services.temporal_service import (
            resolve_sar_temporal_anchor,
            resolve_sar_acquisition_time,
            normalize_to_utc,
        )

        region = payload.region or "Offshore Waters"
        lat = payload.coordinates.latitude if payload.coordinates else None
        lon = payload.coordinates.longitude if payload.coordinates else None
        source_path = payload.source_image_path if (payload.source_image_path and Path(payload.source_image_path).exists()) else None
        obs_time: Optional[datetime] = None
        sar_acq_time: Optional[datetime] = None
        sar_source: Optional[str] = None
        sar_verified: Optional[bool] = None

        if payload.sar_acquisition_time:
            try:
                sar_acq_time = normalize_to_utc(payload.sar_acquisition_time)
                sar_source = payload.sar_acquisition_time_source or "user_provided"
                sar_verified = payload.sar_acquisition_time_verified if payload.sar_acquisition_time_verified is not None else False
                obs_time = sar_acq_time
            except Exception:
                pass

        if payload.observation_timestamp and obs_time is None:
            try:
                obs_time = normalize_to_utc(payload.observation_timestamp)
            except Exception:
                obs_time = None

        tags: Dict[str, Any] = {}
        if source_path and not (lat and lon and obs_time):
            # Inspect uploaded GeoTIFF directly
            try:
                import rasterio
                with rasterio.open(source_path) as src:
                    b = src.bounds
                    if lat is None:
                        lat = float((b.bottom + b.top) / 2.0)
                    if lon is None:
                        lon = float((b.left + b.right) / 2.0)
                    tags = src.tags()
            except Exception as e:
                logger.warning(f"Could not inspect source_path {source_path}: {e}")

        if payload.image_id:
            meta = ImageService.get_image_metadata(payload.image_id)
            if meta:
                if not payload.region or payload.region == "Offshore Waters":
                    region = meta.get("region_name") or region
                if lat is None and meta.get("centroid_lat"):
                    lat = meta["centroid_lat"]
                if lon is None and meta.get("centroid_lon"):
                    lon = meta["centroid_lon"]
                if not source_path and meta.get("file_path"):
                    source_path = meta["file_path"]
                if obs_time is None and meta.get("acquisition_time"):
                    try:
                        obs_time = normalize_to_utc(meta["acquisition_time"])
                    except Exception:
                        pass

        # Resolve authoritative temporal anchor if not explicitly set
        if sar_acq_time is None:
            coords = (lat, lon) if (lat is not None and lon is not None) else None
            anchor = resolve_sar_temporal_anchor(
                image_id=payload.image_id,
                image_path=source_path,
                filename=payload.source_image_path or (meta.get("filename") if payload.image_id and meta else None),
                metadata=tags or payload.metadata,
                investigation_timestamp=obs_time,
                coordinates=coords,
            )
            if anchor["status"] == "resolved" and anchor["sar_acquisition_time"]:
                sar_acq_time = normalize_to_utc(anchor["sar_acquisition_time"])
                sar_source = anchor["source"]
                sar_verified = anchor["verified"]
                obs_time = sar_acq_time

        inv_title = payload.title or payload.name or f"SAR Incident {payload.image_id or inv_id}"

        inv = InvestigationModel(
            investigation_id=inv_id,
            title=inv_title,
            status="Active",
            priority=payload.priority,
            region=region,
            observation_timestamp=obs_time,
            sar_acquisition_time=sar_acq_time,
            sar_acquisition_time_source=sar_source,
            sar_acquisition_time_verified=sar_verified,
            centroid_lat=lat,
            centroid_lon=lon,
            spill_area_km2=0.0,
            metadata_json=payload.metadata,
            image_id=payload.image_id,
            source_image_path=source_path,
            pipeline_status="PENDING",
            pipeline_stages_json={
                "M1 — SAR Ingestion": "PENDING",
                "M2 — U-Net Segmentation": "PENDING",
                "M3 — GIS Geometry": "PENDING",
                "M4 — Ocean Currents": "PENDING",
                "M4 — Lagrangian Drift": "PENDING",
                "M5 — AIS Correlation": "PENDING",
                "REPORT — Forensic Dossier": "PENDING",
            },
            activity_log_json=[
                {
                    "event": "CREATED",
                    "timestamp": now.isoformat(),
                    "details": f"Investigation incident {inv_id} created with priority {payload.priority}.",
                    "user": "Forensic Analyst",
                }
            ],
        )
        self.repo.create(inv)

        try:
            from backend.services.notification_service import NotificationService
            if self.repo.db:
                NotificationService.create_notification(
                    db=self.repo.db,
                    notification_type="NEW_INVESTIGATION",
                    title="New Investigation",
                    message=f"{inv_title} ({inv_id})",
                    investigation_id=inv_id,
                    status="Active",
                    link_path=f"/investigations/{inv_id}",
                    event_key=f"{inv_id}:CREATED",
                )
        except Exception as e:
            logger.warning(f"Failed to emit new investigation notification: {e}")

        return self._to_dict(inv)

    def delete_investigation(self, investigation_id: str, purge: bool = False) -> Dict[str, Any]:
        """Delete an investigation. Soft delete by default, or permanently purge artifacts."""
        rec = self.repo.get_by_id(investigation_id, include_deleted=True)
        if not rec:
            raise InvestigationNotFoundError(f"Investigation '{investigation_id}' not found")

        clean_id = rec.image_id.replace(".tif", "") if rec.image_id else None

        if purge:
            # Delete only investigation-specific generated artifacts
            # Never delete master Sentinel-1 TIFFs, models, or Copernicus ocean datasets
            deleted_files = []
            output_dir = settings.REPO_ROOT / "demo" / "output"
            if output_dir.exists() and clean_id:
                patterns = [
                    f"real_{clean_id}_mask.png",
                    f"real_{clean_id}_mask.tif",
                    f"real_{clean_id}_drift_trajectory.csv",
                    f"real_{clean_id}_drift_trajectory.json",
                    f"real_{clean_id}_result.json",
                    f"real_{clean_id}_layers.geojson",
                    f"OILTRACE_Report_{investigation_id}.md",
                ]
                for p in patterns:
                    target = output_dir / p
                    if target.exists() and target.is_file():
                        try:
                            target.unlink()
                            deleted_files.append(str(target.name))
                        except Exception as e:
                            logger.warning(f"Could not delete artifact {target}: {e}")

            self.repo.hard_delete(investigation_id)
            return {
                "investigation_id": investigation_id,
                "deleted": True,
                "purged": True,
                "message": f"Investigation {investigation_id} permanently purged.",
                "deleted_artifacts": deleted_files,
            }
        else:
            # Soft delete
            self.repo.soft_delete(investigation_id)
            return {
                "investigation_id": investigation_id,
                "deleted": True,
                "purged": False,
                "message": f"Investigation {investigation_id} moved to trash (soft-deleted).",
            }

    def restore_investigation(self, investigation_id: str) -> Dict[str, Any]:
        """Restore a soft-deleted investigation from trash."""
        success = self.repo.restore(investigation_id)
        if not success:
            raise InvestigationNotFoundError(f"Investigation '{investigation_id}' not found in trash.")
        rec = self.repo.get_by_id(investigation_id)
        return self._to_dict(rec)

    def rerun_investigation(self, investigation_id: str) -> Dict[str, Any]:
        """Clone an investigation and spawn a new pipeline run referencing the parent."""
        parent = self.repo.get_by_id(investigation_id, include_deleted=True)
        if not parent:
            raise InvestigationNotFoundError(f"Parent investigation '{investigation_id}' not found")

        now = datetime.now(timezone.utc)
        new_inv_id = f"INV-{now.strftime('%Y')}-{int(now.timestamp()) % 100000:05d}"
        new_title = f"{parent.title} (Re-run)"

        new_inv = InvestigationModel(
            investigation_id=new_inv_id,
            title=new_title,
            status="Active",
            priority=parent.priority,
            region=parent.region,
            observation_timestamp=parent.observation_timestamp,
            centroid_lat=parent.centroid_lat,
            centroid_lon=parent.centroid_lon,
            spill_area_km2=0.0,
            metadata_json=dict(parent.metadata_json or {}),
            image_id=parent.image_id,
            source_image_path=parent.source_image_path,
            pipeline_status="PENDING",
            parent_investigation_id=parent.investigation_id,
            pipeline_stages_json={
                "M1 — SAR Ingestion": "PENDING",
                "M2 — U-Net Segmentation": "PENDING",
                "M3 — GIS Geometry": "PENDING",
                "M4 — Ocean Currents": "PENDING",
                "M4 — Lagrangian Drift": "PENDING",
                "M5 — AIS Correlation": "PENDING",
                "REPORT — Forensic Dossier": "PENDING",
            },
            activity_log_json=[
                {
                    "event": "RERUN_CREATED",
                    "timestamp": now.isoformat(),
                    "details": f"Re-run duplicated from parent investigation #{parent.investigation_id}.",
                    "user": "Forensic Analyst",
                }
            ],
        )
        self.repo.create(new_inv)
        self.repo.append_activity(
            parent.investigation_id,
            "RERUN_SPAWNED",
            f"Duplicated and triggered re-run as #{new_inv_id}.",
        )
        return self._to_dict(new_inv)

    def patch_investigation(self, investigation_id: str, patch: InvestigationPatch) -> Dict[str, Any]:
        """Update mutable properties of an investigation."""
        rec = self.repo.get_by_id(investigation_id, include_deleted=True)
        if not rec:
            raise InvestigationNotFoundError(f"Investigation '{investigation_id}' not found")

        if patch.title is not None:
            rec.title = patch.title
        if patch.priority is not None:
            rec.priority = patch.priority
        if patch.status is not None:
            rec.status = patch.status
        if patch.is_starred is not None:
            rec.is_starred = patch.is_starred
        if patch.is_archived is not None:
            rec.is_archived = patch.is_archived

        self.repo.update(rec)
        return self._to_dict(rec)

    def get_timeline(self, investigation_id: str) -> List[Dict[str, Any]]:
        """Retrieve real chronological activity and execution events for an incident."""
        rec = self.repo.get_by_id(investigation_id, include_deleted=True)
        if not rec:
            raise InvestigationNotFoundError(f"Investigation '{investigation_id}' not found")

        events = list(rec.activity_log_json or [])
        # Add pipeline stage milestones if completed
        stages = rec.pipeline_stages_json or {}
        for stage_name, stage_status in stages.items():
            if stage_status in ("COMPLETED", "PASS", "FAIL"):
                events.append({
                    "event": f"STAGE_{stage_status}",
                    "timestamp": rec.updated_at.isoformat() if rec.updated_at else datetime.now(timezone.utc).isoformat(),
                    "details": f"{stage_name}: {stage_status}",
                    "user": "OILTRACE Pipeline Engine",
                })

        events.sort(key=lambda x: x.get("timestamp") or "", reverse=False)
        return events

    def get_evidence_library(self, investigation_id: str) -> List[Dict[str, Any]]:
        """Compile verified generated artifacts and source evidence for an investigation."""
        rec = self.repo.get_by_id(investigation_id, include_deleted=True)
        if not rec:
            raise InvestigationNotFoundError(f"Investigation '{investigation_id}' not found")

        from backend.services.artifact_service import ArtifactService
        return ArtifactService.compile_investigation_evidence(investigation_id, db=self.db)

    def get_vessel_intelligence(self) -> List[Dict[str, Any]]:
        """Aggregate candidate vessels across all persisted investigations."""
        records = self.repo.list_all(include_deleted=False)
        vessel_map: Dict[Any, Dict[str, Any]] = {}

        for rec in records:
            if not rec.result_json or not isinstance(rec.result_json, dict):
                continue
            candidates = rec.result_json.get("candidate_vessels") or []
            for c in candidates:
                mmsi = c.get("mmsi")
                name = c.get("vessel_name") or "UNKNOWN"
                key = mmsi or name

                dist = float(c.get("min_distance_km") or c.get("distance_to_track_km") or 999.0)
                overall_score = float((c.get("scores") or {}).get("overall") or 0.0)
                conf_score = c.get("confidence_score")
                if conf_score is None:
                    conf_score = round(overall_score * 100, 1)
                else:
                    conf_score = round(float(conf_score), 1)
                conf_level = c.get("confidence_level") or resolve_confidence_level(conf_score)

                incident_entry = {
                    "investigation_id": rec.investigation_id,
                    "title": rec.title,
                    "date": rec.observation_timestamp.isoformat() if rec.observation_timestamp else None,
                    "region": rec.region,
                    "rank": c.get("rank", 0),
                    "min_distance_km": round(dist, 3),
                    "score": round(overall_score, 3),
                    "confidence_score": conf_score,
                    "confidence_level": conf_level,
                }

                if key not in vessel_map:
                    vessel_map[key] = {
                        "mmsi": mmsi,
                        "vessel_name": name,
                        "imo": c.get("imo") or "UNKNOWN",
                        "callsign": c.get("callsign") or "UNKNOWN",
                        "flag": c.get("flag") or "UNKNOWN",
                        "vessel_type": c.get("vessel_type") or "Cargo / Tanker",
                        "appearances_count": 1,
                        "min_distance_km": round(dist, 3),
                        "highest_score": round(overall_score, 3),
                        "confidence_score": conf_score,
                        "confidence_level": conf_level,
                        "last_observed": c.get("timestamp"),
                        "incidents": [incident_entry],
                    }
                else:
                    vessel_map[key]["appearances_count"] += 1
                    if dist < vessel_map[key]["min_distance_km"]:
                        vessel_map[key]["min_distance_km"] = round(dist, 3)
                    if overall_score > vessel_map[key]["highest_score"]:
                        vessel_map[key]["highest_score"] = round(overall_score, 3)
                    if conf_score > vessel_map[key].get("confidence_score", 0.0):
                        vessel_map[key]["confidence_score"] = conf_score
                        vessel_map[key]["confidence_level"] = conf_level
                    vessel_map[key]["incidents"].append(incident_entry)

        aggregated = list(vessel_map.values())
        # Sort by appearances count descending, then min distance ascending
        aggregated.sort(key=lambda x: (-x["appearances_count"], x["min_distance_km"]))
        return aggregated

    def get_investigation_status(self, investigation_id: str) -> Dict[str, Any]:
        """Retrieve execution and lifecycle status of an investigation."""
        rec = self.repo.get_by_id(investigation_id, include_deleted=True)
        if not rec:
            raise InvestigationNotFoundError(
                f"Investigation '{investigation_id}' not found",
                stage="INVESTIGATION_STATUS_LOOKUP",
            )

        stages = rec.pipeline_stages_json or {}
        completed_stages = sum(1 for s in stages.values() if s in ("COMPLETED", "PASS"))
        total_stages = max(len(stages), 1)
        pct = int((completed_stages / total_stages) * 100) if rec.pipeline_status != "COMPLETED" else 100

        return {
            "investigation_id": investigation_id,
            "status": rec.pipeline_status or "PENDING",
            "stage": rec.pipeline_status,
            "progress_percentage": pct,
            "stages": stages,
            "updated_at": rec.updated_at.isoformat() if rec.updated_at else datetime.now(timezone.utc).isoformat(),
            "message": f"Investigation {investigation_id} status is {rec.pipeline_status}",
        }
