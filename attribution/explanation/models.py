"""Data models, contracts, and serialization for Attribution Explanation & Reporting (ATTR-03).

Defines strongly-typed, immutable containers for explainability dossiers,
analytical confidence tiers, and audit-ready incident reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd


class ConfidenceTier(str, Enum):
    """Analytical confidence and correlation tiers for candidate vessel attribution.

    IMPORTANT:
    These tiers represent analytical correlation strength within the evaluated
    spatio-temporal model. They are NOT statistical probabilities of guilt,
    and do NOT establish legal culpability or definitive physical causation.
    """

    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
    MODERATE_CONFIDENCE = "MODERATE_CONFIDENCE"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    NEGLIGIBLE_CORRELATION = "NEGLIGIBLE_CORRELATION"


DEFAULT_ATTRIBUTION_DISCLAIMER: str = (
    "The attribution results are analytical rankings based on the available "
    "spill-origin, AIS, trajectory, temporal, and behavioural evidence. "
    "They do not establish that any vessel caused the spill and should not "
    "be interpreted as proof of responsibility or guilt."
)


def _validate_finite_float(val: Any, field_name: str, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """Validate that a numeric value is finite and bounded."""
    if val is None or isinstance(val, bool):
        raise ValueError(f"{field_name} must be a valid float, got {val}")
    try:
        f_val = float(val)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid float, got {val}") from exc

    if not np.isfinite(f_val):
        raise ValueError(f"{field_name} must be finite, got {f_val}")
    if not (min_val <= f_val <= max_val):
        raise ValueError(f"{field_name} must be within [{min_val}, {max_val}], got {f_val}")
    return f_val


@dataclass(frozen=True)
class CandidateExplanation:
    """Immutable explainability dossier for an individual candidate vessel.

    Attributes:
        mmsi: 9-digit Maritime Mobile Service Identity.
        rank: 1-based attribution rank from ATTR-02.
        vessel_name: Human-readable ship name if available.
        vessel_type: Transmitted ship type code or description.
        overall_score: Composite analytical attribution score [0.0, 1.0].
        confidence_tier: Analytical confidence classification.
        summary_narrative: Professional natural-language explanation paragraph.
        key_supporting_factors: Factual points supporting correlation with the spill.
        key_contradicting_factors: Factual mitigating or non-correlating points.
        data_quality_notes: Telemetry coverage, interpolation, and sensor limitations.
        comparative_note: Qualitative contrast with adjacent ranked candidates.
    """

    mmsi: int
    rank: int
    overall_score: float
    confidence_tier: str
    summary_narrative: str
    vessel_name: Optional[str] = None
    vessel_type: Optional[Union[str, int]] = None
    key_supporting_factors: Tuple[str, ...] = field(default_factory=tuple)
    key_contradicting_factors: Tuple[str, ...] = field(default_factory=tuple)
    data_quality_notes: Tuple[str, ...] = field(default_factory=tuple)
    comparative_note: Optional[str] = None

    def __post_init__(self) -> None:
        # Validate MMSI
        if isinstance(self.mmsi, bool):
            raise ValueError(
                f"mmsi must be a valid positive integer, got boolean {self.mmsi}"
            )

        if isinstance(self.mmsi, (float, np.floating)):
            if not np.isfinite(self.mmsi) or not float(self.mmsi).is_integer():
                raise ValueError(
                    f"mmsi must be a non-fractional integer, got float {self.mmsi}"
                )

        try:
            mmsi_val = int(self.mmsi)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"mmsi must be a valid positive integer, got {self.mmsi}"
            ) from exc

        if isinstance(self.mmsi, str):
            try:
                f_val = float(self.mmsi)
                if not f_val.is_integer():
                    raise ValueError(f"mmsi must be an integer, got '{self.mmsi}'")
            except ValueError as exc:
                raise ValueError(
                    f"mmsi must be an integer, got '{self.mmsi}'"
                ) from exc

        object.__setattr__(self, "mmsi", mmsi_val)
        if self.mmsi <= 0:
            raise ValueError(f"mmsi must be a positive integer, got {self.mmsi}")

        # Validate Rank
        if isinstance(self.rank, bool):
            raise ValueError(f"rank cannot be boolean, got {self.rank}")

        if isinstance(self.rank, (float, np.floating)):
            if not np.isfinite(self.rank) or not float(self.rank).is_integer():
                raise ValueError(f"rank must be an integer, got {self.rank}")

        try:
            rank_val = int(self.rank)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"rank must be an integer >= 1, got {self.rank}") from exc

        object.__setattr__(self, "rank", rank_val)
        if self.rank < 1:
            raise ValueError(f"rank must be an integer >= 1, got {self.rank}")

        # Validate Overall Score
        score_val = _validate_finite_float(self.overall_score, "overall_score", 0.0, 1.0)
        object.__setattr__(self, "overall_score", round(score_val, 4))

        # Validate Confidence Tier
        tier_str = str(self.confidence_tier).strip()
        valid_tiers = {t.value for t in ConfidenceTier}
        if tier_str not in valid_tiers:
            raise ValueError(f"confidence_tier must be one of {sorted(list(valid_tiers))}, got '{tier_str}'")
        object.__setattr__(self, "confidence_tier", tier_str)

        # Validate Narrative
        if not isinstance(self.summary_narrative, str) or not self.summary_narrative.strip():
            raise ValueError("summary_narrative must be a non-empty string")

        # Freeze sequences as tuples
        for field_name in (
            "key_supporting_factors",
            "key_contradicting_factors",
            "data_quality_notes",
        ):
            raw_val = getattr(self, field_name)
            if isinstance(raw_val, (list, tuple, set)):
                object.__setattr__(self, field_name, tuple(str(x) for x in raw_val))
            elif raw_val is None:
                object.__setattr__(self, field_name, tuple())
            else:
                object.__setattr__(self, field_name, (str(raw_val),))

        if self.vessel_name is not None:
            object.__setattr__(self, "vessel_name", str(self.vessel_name).strip() or None)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize CandidateExplanation to a deterministic, JSON-serializable dictionary."""
        return {
            "rank": int(self.rank),
            "mmsi": int(self.mmsi),
            "vessel_name": self.vessel_name,
            "vessel_type": self.vessel_type,
            "overall_score": float(self.overall_score),
            "confidence_tier": str(self.confidence_tier),
            "summary_narrative": str(self.summary_narrative),
            "key_supporting_factors": list(self.key_supporting_factors),
            "key_contradicting_factors": list(self.key_contradicting_factors),
            "data_quality_notes": list(self.data_quality_notes),
            "comparative_note": self.comparative_note,
        }


@dataclass(frozen=True)
class AttributionExplanationReport:
    """Immutable top-level report container for vessel attribution and explainability.

    Attributes:
        incident_summary: Executive overview of the evaluation run.
        origin_summary: Standardized dictionary containing origin coordinates and uncertainty.
        candidate_explanations: Ordered sequence of candidate explanations in rank order.
        top_candidate_summary: Concise narrative focus on Rank #1 if present.
        disclaimer: Mandatory scientific caveat regarding non-causation.
        metadata: Audit metrics, evaluation timestamps, and configuration details.
    """

    incident_summary: str
    origin_summary: Dict[str, Any]
    candidate_explanations: Tuple[CandidateExplanation, ...]
    disclaimer: str = DEFAULT_ATTRIBUTION_DISCLAIMER
    top_candidate_summary: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.incident_summary, str) or not self.incident_summary.strip():
            raise ValueError("incident_summary must be a non-empty string")

        if not isinstance(self.origin_summary, dict):
            raise TypeError(f"origin_summary must be a dictionary, got {type(self.origin_summary)}")

        if not isinstance(self.disclaimer, str) or not self.disclaimer.strip():
            raise ValueError("disclaimer must be a non-empty string")

        # Freeze candidates to tuple
        if isinstance(self.candidate_explanations, (list, tuple)):
            for idx, c in enumerate(self.candidate_explanations):
                if not isinstance(c, CandidateExplanation):
                    raise TypeError(f"Item at index {idx} in candidate_explanations is not a CandidateExplanation")
            object.__setattr__(self, "candidate_explanations", tuple(self.candidate_explanations))
        else:
            raise TypeError("candidate_explanations must be a list or tuple of CandidateExplanation")

    @property
    def total_candidates(self) -> int:
        """Total number of candidates explained in this report."""
        return len(self.candidate_explanations)

    def get_candidate(self, mmsi: int) -> Optional[CandidateExplanation]:
        """Lookup a candidate explanation by MMSI."""
        for cand in self.candidate_explanations:
            if cand.mmsi == mmsi:
                return cand
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize AttributionExplanationReport to a deterministic, JSON-serializable dictionary."""
        return {
            "incident_summary": str(self.incident_summary),
            "origin_summary": dict(self.origin_summary),
            "total_candidates": self.total_candidates,
            "top_candidate_summary": self.top_candidate_summary,
            "candidate_explanations": [c.to_dict() for c in self.candidate_explanations],
            "disclaimer": str(self.disclaimer),
            "metadata": dict(self.metadata),
        }

    def to_dataframe(self) -> pd.DataFrame:
        """Export candidate explanations as a deterministic pandas DataFrame in rank order."""
        if not self.candidate_explanations:
            return pd.DataFrame(
                columns=[
                    "rank",
                    "mmsi",
                    "vessel_name",
                    "vessel_type",
                    "overall_score",
                    "confidence_tier",
                    "summary_narrative",
                    "supporting_factors",
                    "contradicting_factors",
                    "data_quality_notes",
                ]
            )

        rows = []
        for c in self.candidate_explanations:
            rows.append(
                {
                    "rank": c.rank,
                    "mmsi": c.mmsi,
                    "vessel_name": c.vessel_name,
                    "vessel_type": c.vessel_type,
                    "overall_score": c.overall_score,
                    "confidence_tier": c.confidence_tier,
                    "summary_narrative": c.summary_narrative,
                    "supporting_factors": "; ".join(c.key_supporting_factors),
                    "contradicting_factors": "; ".join(c.key_contradicting_factors),
                    "data_quality_notes": "; ".join(c.data_quality_notes),
                }
            )
        return pd.DataFrame(rows)

    def to_markdown(self) -> str:
        """Generate a complete, audit-ready Markdown investigation report."""
        lines: List[str] = [
            "# Marine Oil Spill Attribution & Explainability Report",
            "",
            "## 1. Executive Incident Summary",
            self.incident_summary,
            "",
            "## 2. Estimated Release Origin",
        ]

        lat = self.origin_summary.get("latitude")
        lon = self.origin_summary.get("longitude")
        ts = self.origin_summary.get("timestamp")
        radius = self.origin_summary.get("radius_km")
        conf = self.origin_summary.get("confidence_level")

        lines.extend([
            f"- **Estimated Origin Position:** Latitude {lat:.5f}°, Longitude {lon:.5f}°" if lat is not None and lon is not None else "- **Estimated Origin Position:** Position unavailable",
            f"- **Estimated Release Timestamp:** `{ts}`" if ts is not None else "- **Estimated Release Timestamp:** Unavailable",
            f"- **Uncertainty Radius:** {radius:.2f} km" if radius is not None else "- **Uncertainty Radius:** 0.00 km",
            f"- **Origin Confidence Level:** {conf:.1%}" if conf is not None else "- **Origin Confidence Level:** N/A",
            "",
            "## 3. Candidate Vessel Ranking Summary",
            "",
        ])

        if not self.candidate_explanations:
            lines.append("*No candidate vessels identified within the evaluated spatio-temporal window.*")
        else:
            lines.extend([
                "| Rank | MMSI | Vessel Name | Type | Score | Confidence Tier |",
                "| :---: | :---: | :--- | :--- | :---: | :--- |",
            ])
            for c in self.candidate_explanations:
                vname = c.vessel_name or "Unknown"
                vtype = str(c.vessel_type or "Unknown")
                lines.append(
                    f"| {c.rank} | `{c.mmsi}` | {vname} | {vtype} | {c.overall_score:.4f} | `{c.confidence_tier}` |"
                )

            lines.extend([
                "",
                "## 4. Detailed Candidate Explanations",
                "",
            ])

            for c in self.candidate_explanations:
                vlabel = f"{c.vessel_name} (MMSI: {c.mmsi})" if c.vessel_name else f"MMSI: {c.mmsi}"
                lines.extend([
                    f"### Rank #{c.rank}: {vlabel}",
                    f"- **Analytical Score:** `{c.overall_score:.4f}` | **Confidence Tier:** `{c.confidence_tier}`",
                    "",
                    f"**Summary Narrative:**  ",
                    c.summary_narrative,
                    "",
                ])

                if c.comparative_note:
                    lines.extend([
                        f"**Comparative Assessment:**  ",
                        f"*{c.comparative_note}*",
                        "",
                    ])

                lines.append("**Key Supporting Factors:**")
                if c.key_supporting_factors:
                    for sf in c.key_supporting_factors:
                        lines.append(f"- {sf}")
                else:
                    lines.append("- None noted")
                lines.append("")

                lines.append("**Key Contradicting / Mitigating Factors:**")
                if c.key_contradicting_factors:
                    for cf in c.key_contradicting_factors:
                        lines.append(f"- {cf}")
                else:
                    lines.append("- None noted")
                lines.append("")

                lines.append("**Data Quality & Provenance Notes:**")
                if c.data_quality_notes:
                    for dq in c.data_quality_notes:
                        lines.append(f"- {dq}")
                else:
                    lines.append("- Standard telemetry coverage")
                lines.append("")

        lines.extend([
            "---",
            "## Mandatory Scientific & Legal Disclaimer",
            "> " + self.disclaimer.replace("\n", "\n> "),
            "",
        ])

        return "\n".join(lines)
