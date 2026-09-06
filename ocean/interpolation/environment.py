"""Spatial and temporal interpolation of standardized environmental fields."""

from typing import Any

import numpy as np
import xarray as xr


_COORDINATES = ("time", "latitude", "longitude")
_ACCEPTED_UNITS = {"m/s", "m s-1", "m s^-1", "m s**-1"}
_QUERY_DIMENSION = "particle"


class InterpolationError(ValueError):
    """Raised when an environmental velocity cannot be interpolated safely."""


def interpolate_currents(
    dataset: xr.Dataset, longitude: Any, latitude: Any, time: Any
) -> tuple[float, float] | tuple[np.ndarray, np.ndarray]:
    """Linearly interpolate Copernicus current components at query points.

    Args:
        dataset: Standardized current data containing ``uo`` and ``vo`` in m/s.
        longitude: Scalar or array-like query longitudes.
        latitude: Scalar or array-like query latitudes.
        time: Scalar or array-like query timestamps.

    Returns:
        A scalar ``(u, v)`` tuple for scalar inputs, or paired NumPy arrays for
        array-like inputs. Values remain in m/s.
    """
    return _interpolate(dataset, ("uo", "vo"), longitude, latitude, time)


def interpolate_wind(
    dataset: xr.Dataset, longitude: Any, latitude: Any, time: Any
) -> tuple[float, float] | tuple[np.ndarray, np.ndarray]:
    """Linearly interpolate ERA5 10-m wind components at query points.

    Args:
        dataset: Standardized wind data containing ``u10`` and ``v10`` in m/s.
        longitude: Scalar or array-like query longitudes.
        latitude: Scalar or array-like query latitudes.
        time: Scalar or array-like query timestamps.

    Returns:
        A scalar ``(u, v)`` tuple for scalar inputs, or paired NumPy arrays for
        array-like inputs. Values remain in m/s.
    """
    return _interpolate(dataset, ("u10", "v10"), longitude, latitude, time)


def _interpolate(
    dataset: xr.Dataset,
    variable_names: tuple[str, str],
    longitude: Any,
    latitude: Any,
    time: Any,
) -> tuple[float, float] | tuple[np.ndarray, np.ndarray]:
    """Validate a field and perform paired linear xarray interpolation."""
    _validate_dataset(dataset, variable_names)
    longitude_values, latitude_values, time_values, output_shape, scalar = _prepare_queries(
        longitude, latitude, time
    )
    time_values = time_values.astype(dataset["time"].dtype)
    _validate_query_bounds(dataset, longitude_values, latitude_values, time_values)

    query = {
        "longitude": xr.DataArray(longitude_values, dims=_QUERY_DIMENSION),
        "latitude": xr.DataArray(latitude_values, dims=_QUERY_DIMENSION),
        "time": xr.DataArray(time_values, dims=_QUERY_DIMENSION),
    }
    result = dataset[list(variable_names)].interp(query, method="linear")
    first = np.asarray(result[variable_names[0]].values)
    second = np.asarray(result[variable_names[1]].values)

    if np.isnan(first).any() or np.isnan(second).any():
        raise InterpolationError(
            "Interpolation produced NaN environmental velocity values; "
            "required surrounding data may be missing."
        )

    if scalar:
        return float(first.item()), float(second.item())
    return first.reshape(output_shape), second.reshape(output_shape)


def _validate_dataset(dataset: xr.Dataset, variable_names: tuple[str, str]) -> None:
    """Validate the standardized field contract required for interpolation."""
    for variable_name in variable_names:
        if variable_name not in dataset.data_vars:
            raise InterpolationError(f"Required environmental variable '{variable_name}' is missing.")
        _validate_units(dataset[variable_name], variable_name)

    for coordinate_name in _COORDINATES:
        if coordinate_name not in dataset.coords:
            raise InterpolationError(f"Required coordinate '{coordinate_name}' is missing.")
        coordinate = dataset[coordinate_name]
        if coordinate.ndim != 1:
            raise InterpolationError(
                f"Coordinate '{coordinate_name}' must be one-dimensional; "
                f"received {coordinate.ndim} dimensions."
            )

    _validate_monotonic(dataset["latitude"], "latitude", allow_decreasing=True)
    _validate_monotonic(dataset["longitude"], "longitude", allow_decreasing=True)
    _validate_monotonic(dataset["time"], "time", allow_decreasing=False)

    for variable_name in variable_names:
        dimensions = set(dataset[variable_name].dims)
        required = set(_COORDINATES)
        if dimensions != required:
            raise InterpolationError(
                f"Environmental variable '{variable_name}' must have dimensions "
                f"(time, latitude, longitude); received {dataset[variable_name].dims}."
            )


def _validate_units(variable: xr.DataArray, variable_name: str) -> None:
    """Require a recognized metres-per-second unit without converting values."""
    units = variable.attrs.get("units")
    normalized = str(units).strip().lower() if units is not None else None
    if normalized not in _ACCEPTED_UNITS:
        raise InterpolationError(
            f"Environmental variable '{variable_name}' must use metres-per-second "
            f"units; received {units!r}."
        )


def _validate_monotonic(
    coordinate: xr.DataArray, name: str, *, allow_decreasing: bool
) -> None:
    """Ensure an interpolation coordinate is monotonic."""
    index = coordinate.to_index()
    valid = index.is_monotonic_increasing or (
        allow_decreasing and index.is_monotonic_decreasing
    )
    if not valid:
        direction = "monotonic" if allow_decreasing else "monotonically increasing"
        raise InterpolationError(f"Coordinate '{name}' must be {direction}.")


def _prepare_queries(
    longitude: Any, latitude: Any, time: Any
) -> tuple[np.ndarray, np.ndarray, np.ndarray, tuple[int, ...], bool]:
    """Broadcast scalar or array-like particle queries while preserving order."""
    try:
        longitude_values, latitude_values, time_values = np.broadcast_arrays(
            np.asarray(longitude, dtype=float),
            np.asarray(latitude, dtype=float),
            np.asarray(time, dtype="datetime64[ns]"),
        )
    except (TypeError, ValueError) as error:
        raise InterpolationError(
            "Longitude, latitude, and time queries must be broadcast-compatible "
            "numeric coordinates and valid timestamps."
        ) from error

    if not np.isfinite(longitude_values).all() or not np.isfinite(latitude_values).all():
        raise InterpolationError("Longitude and latitude query values must be finite.")
    if np.isnat(time_values).any():
        raise InterpolationError("Time query values must be valid timestamps.")

    scalar = longitude_values.ndim == 0
    return (
        longitude_values.reshape(-1),
        latitude_values.reshape(-1),
        time_values.reshape(-1),
        longitude_values.shape,
        scalar,
    )


def _validate_query_bounds(
    dataset: xr.Dataset,
    longitude: np.ndarray,
    latitude: np.ndarray,
    time: np.ndarray,
) -> None:
    """Reject queries outside the observed domain before calling xarray.interp."""
    _validate_bounds(longitude, dataset["longitude"].values, "longitude")
    _validate_bounds(latitude, dataset["latitude"].values, "latitude")
    _validate_bounds(time, dataset["time"].values, "time")


def _validate_bounds(values: np.ndarray, coordinate: np.ndarray, name: str) -> None:
    """Raise a clear error when any query lies outside one coordinate range."""
    minimum = coordinate.min()
    maximum = coordinate.max()
    if (values < minimum).any() or (values > maximum).any():
        raise InterpolationError(
            f"Query {name} is outside the available dataset range "
            f"[{minimum}, {maximum}]."
        )
