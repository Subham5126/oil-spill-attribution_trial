"""Sentinel-1 SAR scene tiling, patch extraction, and reassembly.

This module partitions large (2, H, W) SAR scenes into smaller model-ready
patches (e.g. 256x256 or 512x512) for the AI/U-Net segmentation module,
preserving complete geospatial provenance, pixel offset indices, and
reassembly metadata.
"""

from dataclasses import dataclass, field
from typing import Any, Iterator, Literal
import numpy as np

try:
    from rasterio.transform import Affine
    from rasterio.windows import Window, bounds as window_bounds, transform as window_transform
    _RASTERIO_AVAILABLE = True
except ImportError:
    _RASTERIO_AVAILABLE = False

from satellite.sentinel1.exceptions import Sentinel1DataError


@dataclass(frozen=True)
class TileMetadata:
    """Geospatial and spatial indexing metadata for an individual tile."""

    scene_id: str
    tile_id: str
    row_idx: int
    col_idx: int
    pixel_row_start: int
    pixel_row_end: int
    pixel_col_start: int
    pixel_col_end: int
    tile_height: int
    tile_width: int
    scene_dimensions: tuple[int, int]
    tile_size: int
    stride: int
    overlap: int
    is_padded: bool
    valid_region: tuple[int, int, int, int]  # (row_start, row_end, col_start, col_end) relative to tile
    crs: str | None = None
    transform: tuple[float, float, float, float, float, float] | None = None
    bounds: tuple[float, float, float, float] | None = None
    acquisition_time: Any | None = None
    pixel_spacing: tuple[float, float] | None = None
    pixel_resolution: tuple[float, float] | None = None
    bands: tuple[str, str] = ("VV", "VH")
    polarization_order: tuple[str, str] = ("VV", "VH")
    unit: str = "dB"
    dtype: str = "float32"


@dataclass
class TileItem:
    """Container holding a tile array and its corresponding metadata."""

    image: np.ndarray  # Shape: (2, tile_size, tile_size), float32
    metadata: TileMetadata


@dataclass
class TilingConfig:
    """Configuration for scene tiling and patch extraction."""

    tile_size: int = 256
    stride: int | None = None  # None defaults to tile_size (no overlap)
    pad_mode: Literal["constant", "reflect", "edge"] = "constant"
    pad_value: float = -50.0  # Default SAR noise floor dB

    def __post_init__(self):
        """Validate tile size and stride parameters."""
        if self.tile_size <= 0:
            raise Sentinel1DataError(f"tile_size must be positive; got {self.tile_size}.")

        if self.stride is None:
            self.stride = self.tile_size
        elif self.stride <= 0:
            raise Sentinel1DataError(f"stride must be positive; got {self.stride}.")
        elif self.stride > self.tile_size:
            raise Sentinel1DataError(
                f"stride ({self.stride}) cannot be greater than tile_size ({self.tile_size})."
            )

    @property
    def overlap(self) -> int:
        """Overlap in pixels between consecutive tiles."""
        assert self.stride is not None
        return self.tile_size - self.stride


def _compute_geospatial_for_tile(
    scene_transform: tuple[float, float, float, float, float, float] | None,
    col_start: int,
    row_start: int,
    valid_width: int,
    valid_height: int,
) -> tuple[tuple[float, float, float, float, float, float] | None, tuple[float, float, float, float] | None]:
    """Calculate the affine transform and geographic bounds for a tile.

    Uses rasterio window transforms when available; otherwise falls back to
    standard 2D affine matrix math.
    """
    if scene_transform is None or len(scene_transform) != 6:
        return None, None

    if _RASTERIO_AVAILABLE:
        try:
            aff = Affine(*scene_transform)
            win = Window(
                col_off=col_start,
                row_off=row_start,
                width=valid_width,
                height=valid_height,
            )
            t_win = window_transform(win, aff)
            b_win = window_bounds(win, aff)
            return tuple(t_win)[:6], (b_win[0], b_win[1], b_win[2], b_win[3])
        except Exception:
            pass

    # Standard affine fallback:
    # x' = a * col + b * row + c
    # y' = d * col + e * row + f
    a, b, c, d, e, f = scene_transform
    new_c = a * col_start + b * row_start + c
    new_f = d * col_start + e * row_start + f
    tile_transform = (a, b, new_c, d, e, new_f)

    # Compute 4 corner points
    corners_col = [0, valid_width, valid_width, 0]
    corners_row = [0, 0, valid_height, valid_height]
    xs = [a * c_pt + b * r_pt + new_c for c_pt, r_pt in zip(corners_col, corners_row)]
    ys = [d * c_pt + e * r_pt + new_f for c_pt, r_pt in zip(corners_col, corners_row)]
    bounds = (min(xs), min(ys), max(xs), max(ys))

    return tile_transform, bounds


class SceneTiler:
    """Extracts patches and coordinates from dual-channel Sentinel-1 SAR scenes."""

    def __init__(self, config: TilingConfig | None = None):
        """Initialize the SceneTiler.

        Args:
            config: Tiling configuration. If None, default 256x256 no-overlap is used.
        """
        self.config = config or TilingConfig()

    def generate_tiles(
        self,
        image: np.ndarray,
        scene_metadata: dict[str, Any] | None = None,
    ) -> Iterator[TileItem]:
        """Generate tile items one at a time to minimize memory consumption.

        Args:
            image: SAR array of shape (2, H, W) with channel 0=VV and channel 1=VH.
            scene_metadata: Optional metadata dictionary from the Sentinel-1 loader.

        Yields:
            TileItem instances containing the (2, tile_size, tile_size) float32 array
            and complete TileMetadata.
        """
        if not isinstance(image, np.ndarray):
            raise Sentinel1DataError(f"Input must be a numpy.ndarray; got {type(image)}.")

        if image.ndim != 3 or image.shape[0] != 2:
            raise Sentinel1DataError(
                f"Expected array of shape (2, H, W) for (VV, VH) channels; got shape {image.shape}."
            )

        _, height, width = image.shape
        if height <= 0 or width <= 0:
            raise Sentinel1DataError(f"Invalid image dimensions: ({height}, {width}).")

        tile_size = self.config.tile_size
        stride = self.config.stride or tile_size
        overlap = self.config.overlap

        # Extract scene context
        scene_id = "scene"
        scene_crs = None
        scene_transform = None
        scene_acq_time = None
        scene_spacing = None
        scene_resolution = None
        scene_bands = ("VV", "VH")
        scene_pol = ("VV", "VH")
        scene_unit = "dB"
        scene_dtype = "float32"

        if scene_metadata:
            scene_id = str(scene_metadata.get("scene_id") or "scene")
            scene_crs = scene_metadata.get("crs")
            scene_transform = scene_metadata.get("transform")
            scene_acq_time = scene_metadata.get("acquisition_time")
            scene_spacing = scene_metadata.get("pixel_spacing")
            scene_resolution = scene_metadata.get("pixel_resolution") or scene_spacing
            if scene_metadata.get("bands"):
                scene_bands = tuple(scene_metadata["bands"])
            if scene_metadata.get("polarization_order"):
                scene_pol = tuple(scene_metadata["polarization_order"])
            if scene_metadata.get("unit"):
                scene_unit = str(scene_metadata["unit"])
            if scene_metadata.get("dtype"):
                scene_dtype = str(scene_metadata["dtype"])

        row_starts = list(range(0, height, stride))
        col_starts = list(range(0, width, stride))

        for row_idx, r_start in enumerate(row_starts):
            r_end_raw = min(r_start + tile_size, height)
            valid_h = r_end_raw - r_start

            for col_idx, c_start in enumerate(col_starts):
                c_end_raw = min(c_start + tile_size, width)
                valid_w = c_end_raw - c_start

                # Slice valid data
                valid_patch = image[:, r_start:r_end_raw, c_start:c_end_raw]

                # Determine if padding is needed
                is_padded = (valid_h < tile_size) or (valid_w < tile_size)

                if is_padded:
                    pad_h = tile_size - valid_h
                    pad_w = tile_size - valid_w
                    if self.config.pad_mode == "constant":
                        tile_arr = np.full(
                            (2, tile_size, tile_size),
                            fill_value=self.config.pad_value,
                            dtype=np.float32,
                        )
                        tile_arr[:, :valid_h, :valid_w] = valid_patch
                    else:
                        tile_arr = np.pad(
                            valid_patch,
                            ((0, 0), (0, pad_h), (0, pad_w)),
                            mode=self.config.pad_mode,
                        ).astype(np.float32)
                else:
                    tile_arr = valid_patch.astype(np.float32, copy=True)

                # Geospatial transform and bounds for this tile
                t_transform, t_bounds = _compute_geospatial_for_tile(
                    scene_transform=scene_transform,
                    col_start=c_start,
                    row_start=r_start,
                    valid_width=valid_w,
                    valid_height=valid_h,
                )

                tile_id = f"{scene_id}_r{row_idx:03d}_c{col_idx:03d}"
                metadata = TileMetadata(
                    scene_id=scene_id,
                    tile_id=tile_id,
                    row_idx=row_idx,
                    col_idx=col_idx,
                    pixel_row_start=r_start,
                    pixel_row_end=r_end_raw,
                    pixel_col_start=c_start,
                    pixel_col_end=c_end_raw,
                    tile_height=tile_size,
                    tile_width=tile_size,
                    scene_dimensions=(height, width),
                    tile_size=tile_size,
                    stride=stride,
                    overlap=overlap,
                    is_padded=is_padded,
                    valid_region=(0, valid_h, 0, valid_w),
                    crs=scene_crs,
                    transform=t_transform,
                    bounds=t_bounds,
                    acquisition_time=scene_acq_time,
                    pixel_spacing=scene_spacing,
                    pixel_resolution=scene_resolution,
                    bands=scene_bands,
                    polarization_order=scene_pol,
                    unit=scene_unit,
                    dtype=scene_dtype,
                )

                yield TileItem(image=tile_arr, metadata=metadata)

    def tile_scene(
        self,
        image: np.ndarray,
        scene_metadata: dict[str, Any] | None = None,
    ) -> list[TileItem]:
        """Tile a scene and return all tiles in a list.

        Args:
            image: Array of shape (2, H, W).
            scene_metadata: Optional metadata dictionary.

        Returns:
            List of TileItem instances.
        """
        return list(self.generate_tiles(image, scene_metadata))


def reassemble_tiles(
    tiles: list[TileItem] | list[np.ndarray],
    metadata_list: list[TileMetadata] | list[dict[str, Any]],
    scene_dimensions: tuple[int, int] | None = None,
    channels: int | None = None,
    blend_mode: Literal["overwrite", "average"] = "overwrite",
) -> np.ndarray:
    """Reassemble extracted tiles back into the original full scene dimensions.

    This function supports reassembling both multi-channel SAR backscatter arrays
    and single-channel segmentation masks produced by downstream AI models.

    Args:
        tiles: List of TileItem instances or raw NumPy tile arrays of shape (C, H, W) or (H, W).
        metadata_list: List of TileMetadata or metadata dictionaries corresponding to each tile.
        scene_dimensions: (height, width) of full scene. If None, inferred from metadata.
        channels: Number of channels in reconstructed array. Inferred if None.
        blend_mode: 'overwrite' replaces pixels; 'average' averages overlapping regions.

    Returns:
        Reconstructed NumPy array of shape (C, height, width) with float32 dtype.

    Raises:
        Sentinel1DataError: If tile count and metadata count mismatch or dimensions are missing.
    """
    if len(tiles) != len(metadata_list):
        raise Sentinel1DataError(
            f"Mismatch between number of tiles ({len(tiles)}) and metadata entries ({len(metadata_list)})."
        )

    if not tiles:
        raise Sentinel1DataError("Cannot reassemble an empty list of tiles.")

    # Standardize first tile and metadata
    first_tile = tiles[0].image if isinstance(tiles[0], TileItem) else tiles[0]
    first_meta = tiles[0].metadata if isinstance(tiles[0], TileItem) else metadata_list[0]

    # Determine channel count and dimensions
    is_2d = (first_tile.ndim == 2)
    if is_2d:
        actual_channels = 1
    else:
        actual_channels = first_tile.shape[0]

    target_channels = channels or actual_channels

    if scene_dimensions is None:
        if isinstance(first_meta, TileMetadata):
            scene_dimensions = first_meta.scene_dimensions
        elif isinstance(first_meta, dict) and "scene_dimensions" in first_meta:
            scene_dimensions = tuple(first_meta["scene_dimensions"])
        else:
            raise Sentinel1DataError(
                "scene_dimensions must be provided explicitly if not present in metadata."
            )

    full_h, full_w = scene_dimensions

    out = np.zeros((target_channels, full_h, full_w), dtype=np.float32)
    weight_map = np.zeros((full_h, full_w), dtype=np.float32) if blend_mode == "average" else None

    for item, meta in zip(tiles, metadata_list):
        t_arr = item.image if isinstance(item, TileItem) else item
        m = item.metadata if isinstance(item, TileItem) else meta

        if isinstance(m, dict):
            r_start = m["pixel_row_start"]
            r_end = m["pixel_row_end"]
            c_start = m["pixel_col_start"]
            c_end = m["pixel_col_end"]
            v_reg = m.get("valid_region", (0, r_end - r_start, 0, c_end - c_start))
        else:
            r_start = m.pixel_row_start
            r_end = m.pixel_row_end
            c_start = m.pixel_col_start
            c_end = m.pixel_col_end
            v_reg = m.valid_region

        vr_start, vr_end, vc_start, vc_end = v_reg
        valid_tile_patch = t_arr[:, vr_start:vr_end, vc_start:vc_end] if not is_2d else t_arr[vr_start:vr_end, vc_start:vc_end]

        if is_2d:
            valid_tile_patch = valid_tile_patch[np.newaxis, ...]

        if blend_mode == "average":
            assert weight_map is not None
            out[:, r_start:r_end, c_start:c_end] += valid_tile_patch
            weight_map[r_start:r_end, c_start:c_end] += 1.0
        else:
            out[:, r_start:r_end, c_start:c_end] = valid_tile_patch

    if blend_mode == "average":
        assert weight_map is not None
        mask = weight_map > 0
        for c in range(target_channels):
            out[c, mask] /= weight_map[mask]

    return out
