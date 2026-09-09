"""AI / U-Net Model Interface and Adapter for Sentinel-1 SAR tiles.

This module provides a validated, contract-compliant bridge between the
Sentinel-1 satellite module (M2) and the downstream AI/U-Net segmentation module (M1).

Key capabilities:
- Validates model input shape: strictly channel-first (2, H, W); rejects channel-last (H, W, 2).
- Validates channel count: strictly 2 channels (Channel 0 = VV, Channel 1 = VH).
- Validates data type: float32.
- Validates finite values: strictly finite (no NaN, +inf, -inf).
- Validates and preserves complete geospatial/temporal metadata for downstream GIS mapping.
- Standardizes tile handoff into AIReadyTile and batched arrays for inference.
"""

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from typing import Any, Sequence
import numpy as np

from satellite.sentinel1.exceptions import Sentinel1DataError, Sentinel1MetadataError
from .tiling import TileItem, TileMetadata


@dataclass(frozen=True)
class AIReadyTile:
    """Standardized, model-ready container for an individual SAR tile and its metadata.

    Attributes:
        image: NumPy array of shape (2, H, W) and dtype float32, contiguous in memory.
               Channel 0 is VV; Channel 1 is VH.
        metadata: Comprehensive metadata dictionary preserving scene, tile, geospatial,
                  and temporal provenance.
    """

    image: np.ndarray
    metadata: dict[str, Any]

    @property
    def shape(self) -> tuple[int, ...]:
        """Return array shape (2, H, W)."""
        return self.image.shape

    @property
    def channels(self) -> int:
        """Return number of channels (always 2)."""
        return self.image.shape[0]

    @property
    def height(self) -> int:
        """Return tile height."""
        return self.image.shape[1]

    @property
    def width(self) -> int:
        """Return tile width."""
        return self.image.shape[2]

    @property
    def tile_id(self) -> str:
        """Return unique tile ID."""
        return str(self.metadata.get("tile_id", "unknown_tile"))

    @property
    def scene_id(self) -> str:
        """Return source scene ID."""
        return str(self.metadata.get("scene_id", "unknown_scene"))

    @property
    def crs(self) -> str | None:
        """Return coordinate reference system."""
        return self.metadata.get("crs")

    @property
    def transform(self) -> tuple[float, float, float, float, float, float] | None:
        """Return affine transform tuple."""
        return self.metadata.get("transform")

    @property
    def bounds(self) -> tuple[float, float, float, float] | None:
        """Return geographic bounding box (minx, miny, maxx, maxy)."""
        return self.metadata.get("bounds")

    @property
    def acquisition_time(self) -> datetime | None:
        """Return UTC acquisition timestamp."""
        return self.metadata.get("acquisition_time")

    def to_geojson(self) -> dict[str, Any]:
        """Convert this tile's metadata into a GeoJSON Feature dictionary."""
        from satellite.sentinel1.geojson import tile_metadata_to_geojson
        return tile_metadata_to_geojson(self.metadata)

    def as_dict(self, include_geojson: bool = False) -> dict[str, Any]:
        """Return representation as a standard Python dictionary.

        Args:
            include_geojson: If True, includes 'geojson' Feature in the output.
        """
        out = {
            "image": self.image,
            "metadata": dict(self.metadata),
        }
        if include_geojson:
            out["geojson"] = self.to_geojson()
        return out

    def to_numpy(self) -> np.ndarray:
        """Return raw NumPy array of shape (2, H, W)."""
        return self.image

    def to_tensor(self) -> Any:
        """Convert image array to a PyTorch tensor if torch is installed.

        Returns:
            torch.Tensor of shape (2, H, W) and dtype torch.float32.

        Raises:
            ImportError: If PyTorch is not installed in the environment.
        """
        try:
            
            import torch
            return torch.from_numpy(self.image)
        except ImportError as exc:
            raise ImportError(
                "PyTorch is not installed in the current environment. "
                "Use `to_numpy()` or install `torch` to enable tensor conversion."
            ) from exc


def validate_model_input(
    image: np.ndarray,
    metadata: TileMetadata | dict[str, Any] | None = None,
    check_finite: bool = True,
) -> None:
    """Validate that a SAR array and metadata strictly comply with the AI model contract.

    Validation rules:
    1. Input must be a numpy.ndarray.
    2. Array must have exactly 3 dimensions.
    3. Specifically rejects channel-last (H, W, 2) arrays.
    4. Channel count must be exactly 2.
    5. Spatial dimensions H and W must be positive.
    6. Dtype must be float32.
    7. Values must be finite (no NaN, +Inf, -Inf) if check_finite is True.
    8. Channel order must be Channel 0 = VV and Channel 1 = VH if metadata is provided.
    9. Acquisition timestamp (if present in metadata) must be timezone-aware UTC.

    Args:
        image: SAR array to validate.
        metadata: Optional tile or scene metadata.
        check_finite: Whether to verify that all pixel values are finite.

    Raises:
        Sentinel1DataError: If array shape, channels, dtype, or values violate the contract.
        Sentinel1MetadataError: If metadata channel ordering or timestamps are invalid.
    """
    if not isinstance(image, np.ndarray):
        raise Sentinel1DataError(f"Expected image to be a numpy.ndarray; got {type(image).__name__}.")

    if image.ndim != 3:
        raise Sentinel1DataError(
            f"Expected 3D array of shape (2, H, W); got array with {image.ndim} dimensions and shape {image.shape}."
        )

    # Check for accidental channel-last layout (H, W, 2)
    if image.shape[2] == 2 and image.shape[0] != 2:
        raise Sentinel1DataError(
            f"Detected channel-last shape {image.shape}; AI contract strictly requires "
            f"channel-first layout (2, H, W)."
        )

    # Check channel count
    if image.shape[0] != 2:
        raise Sentinel1DataError(
            f"Expected exactly 2 channels (VV, VH); got {image.shape[0]} channels in shape {image.shape}."
        )

    _, height, width = image.shape
    if height <= 0 or width <= 0:
        raise Sentinel1DataError(f"Invalid spatial dimensions: height={height}, width={width}. Must be positive.")

    # Check dtype
    if image.dtype != np.float32:
        raise Sentinel1DataError(
            f"Expected float32 array; got {image.dtype}. AI contract requires 32-bit floating point."
        )

    # Check finite values
    if check_finite:
        if not np.all(np.isfinite(image)):
            has_nan = bool(np.isnan(image).any())
            has_inf = bool(np.isinf(image).any())
            err_details = []
            if has_nan:
                err_details.append("NaN")
            if has_inf:
                err_details.append("Inf")
            raise Sentinel1DataError(
                f"Model input contains non-finite values ({', '.join(err_details)}). "
                f"Preprocessing cleaning must be applied prior to model handoff."
            )

    # Validate metadata if provided
    if metadata is not None:
        meta_dict: dict[str, Any]
        if is_dataclass(metadata) and not isinstance(metadata, type):
            meta_dict = asdict(metadata)
        elif isinstance(metadata, dict):
            meta_dict = metadata
        else:
            meta_dict = {}

        # Check channel ordering
        pol_order = meta_dict.get("polarization_order") or meta_dict.get("bands")
        if pol_order is not None:
            pol_tuple = tuple(pol_order)
            if len(pol_tuple) >= 2 and (pol_tuple[0] != "VV" or pol_tuple[1] != "VH"):
                raise Sentinel1DataError(
                    f"Channel order mismatch: expected ('VV', 'VH'); metadata specifies {pol_tuple}."
                )

        # Check timestamp timezone
        acq_time = meta_dict.get("acquisition_time")
        if acq_time is not None:
            if isinstance(acq_time, datetime):
                if acq_time.tzinfo is None or acq_time.utcoffset() != timezone.utc.utcoffset(acq_time):
                    raise Sentinel1MetadataError(
                        f"Acquisition time must be timezone-aware UTC; got {acq_time} with tzinfo={acq_time.tzinfo}."
                    )


def prepare_for_model(
    tile: TileItem | np.ndarray,
    metadata: TileMetadata | dict[str, Any] | None = None,
    check_finite: bool = True,
) -> AIReadyTile:
    """Prepare and validate a satellite tile for the AI/U-Net segmentation module.

    Accepts either a TileItem or a raw (2, H, W) numpy array with optional metadata,
    validates adherence to the AI contract, ensures memory is C-contiguous, and bundles
    all required metadata into a standardized AIReadyTile.

    Args:
        tile: TileItem instance or (2, H, W) numpy array.
        metadata: Optional metadata if tile is a raw array.
        check_finite: Whether to enforce finite value checks.

    Returns:
        AIReadyTile satisfying all AI module input specifications.

    Raises:
        Sentinel1DataError: If array violates shape, channels, dtype, or finite rules.
        Sentinel1MetadataError: If metadata violates channel or timezone constraints.
    """
    if isinstance(tile, TileItem):
        image = tile.image
        input_meta = tile.metadata
    elif isinstance(tile, np.ndarray):
        image = tile
        input_meta = metadata
    else:
        raise Sentinel1DataError(f"Expected TileItem or numpy.ndarray; got {type(tile).__name__}.")

    # Validate against contract
    validate_model_input(image, metadata=input_meta, check_finite=check_finite)

    # Normalize metadata to dictionary
    clean_meta: dict[str, Any] = {}
    if is_dataclass(input_meta) and not isinstance(input_meta, type):
        clean_meta = asdict(input_meta)
    elif isinstance(input_meta, dict):
        clean_meta = dict(input_meta)

    # Ensure required default metadata fields
    clean_meta.setdefault("scene_id", "scene")
    clean_meta.setdefault("tile_id", "tile_000")
    clean_meta.setdefault("bands", ("VV", "VH"))
    clean_meta.setdefault("polarization_order", ("VV", "VH"))
    clean_meta.setdefault("dtype", "float32")
    clean_meta.setdefault("tile_dimensions", (image.shape[1], image.shape[2]))

    # Ensure memory is contiguous float32
    contiguous_image = np.ascontiguousarray(image, dtype=np.float32)

    return AIReadyTile(image=contiguous_image, metadata=clean_meta)


def batch_for_model(
    tiles: Sequence[AIReadyTile | TileItem | np.ndarray],
    metadata_list: Sequence[TileMetadata | dict[str, Any]] | None = None,
    check_finite: bool = True,
) -> dict[str, Any]:
    """Stack multiple tiles into a batched representation for model inference.

    Args:
        tiles: Sequence of AIReadyTile, TileItem, or (2, H, W) numpy arrays.
        metadata_list: Optional list of metadata dictionaries if tiles are raw arrays.
        check_finite: Whether to verify finite values for each tile.

    Returns:
        Dictionary with:
            "images": np.ndarray of shape (B, 2, H, W) and dtype float32.
            "metadata": list of metadata dictionaries corresponding to each batch item.

    Raises:
        Sentinel1DataError: If tile list is empty or tile shapes are heterogeneous.
    """
    if not tiles:
        raise Sentinel1DataError("Cannot create batch from empty tile sequence.")

    ready_tiles: list[AIReadyTile] = []
    for idx, item in enumerate(tiles):
        item_meta = None
        if metadata_list is not None and idx < len(metadata_list):
            item_meta = metadata_list[idx]

        if isinstance(item, AIReadyTile):
            ready_tiles.append(item)
        else:
            ready_tile = prepare_for_model(item, metadata=item_meta, check_finite=check_finite)
            ready_tiles.append(ready_tile)

    # Verify all tiles have matching dimensions
    ref_shape = ready_tiles[0].shape
    for idx, t in enumerate(ready_tiles[1:], start=1):
        if t.shape != ref_shape:
            raise Sentinel1DataError(
                f"Batch tile shape mismatch: tile 0 has shape {ref_shape}, but tile {idx} has shape {t.shape}."
            )

    batch_array = np.stack([t.image for t in ready_tiles], axis=0)
    batch_metadata = [t.metadata for t in ready_tiles]

    return {
        "images": batch_array,
        "metadata": batch_metadata,
    }
