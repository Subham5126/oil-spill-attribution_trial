"""Validation and loading for ERA5 10-m wind data."""

from pathlib import Path

import xarray as xr


_REQUIRED_VARIABLES = ("u10", "v10")
_REQUIRED_COORDINATES = ("time", "latitude", "longitude")
_OUTPUT_DIMENSIONS = ("time", "latitude", "longitude")
_ACCEPTED_WIND_UNITS = {"m/s", "m s-1", "m s^-1", "m s**-1"}


class WindDataError(ValueError):
    """Raised when a dataset cannot be used as ERA5 10-m wind input."""


def load_wind(path: str | Path) -> xr.Dataset:
    """Load validated ERA5 10-m wind data into memory.

    ERA5's ``valid_time`` coordinate is standardized to ``time``. The returned
    dataset contains only ``u10`` and ``v10``, each ordered as ``(time,
    latitude, longitude)`` with units standardized to ``m/s``. This loader does
    not interpolate, fill missing data, or modify wind values.

    Args:
        path: Path to an ERA5 NetCDF file.

    Raises:
        FileNotFoundError: If ``path`` does not exist or is not a file.
        WindDataError: If the dataset does not satisfy the ERA5 wind contract.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Wind NetCDF file does not exist: {file_path}")

    try:
        with xr.open_dataset(file_path) as source:
            dataset = source.load()
    except (OSError, ValueError) as error:
        raise WindDataError(
            f"Unable to open wind NetCDF file '{file_path}': {error}"
        ) from error

    dataset = _standardize_time_coordinate(dataset)
    _validate_dataset(dataset)
    wind = dataset[list(_REQUIRED_VARIABLES)]

    for variable_name in _REQUIRED_VARIABLES:
        wind[variable_name] = wind[variable_name].transpose(*_OUTPUT_DIMENSIONS)
        wind[variable_name].attrs["units"] = "m/s"

    return wind


def _standardize_time_coordinate(dataset: xr.Dataset) -> xr.Dataset:
    """Rename ERA5's ``valid_time`` coordinate to the standard ``time`` name."""
    has_time = "time" in dataset.coords
    has_valid_time = "valid_time" in dataset.coords
    if not has_time and not has_valid_time:
        raise WindDataError("Required time coordinate 'time' or 'valid_time' is missing.")
    if has_time and has_valid_time:
        raise WindDataError(
            "Dataset contains both 'time' and 'valid_time' coordinates; "
            "the time coordinate is ambiguous."
        )
    if has_valid_time:
        return dataset.rename({"valid_time": "time"})
    return dataset


def _validate_dataset(dataset: xr.Dataset) -> None:
    """Validate the structural and physical metadata contract for ERA5 wind."""
    for variable_name in _REQUIRED_VARIABLES:
        if variable_name not in dataset.data_vars:
            raise WindDataError(f"Required wind variable '{variable_name}' is missing.")

    for coordinate_name in _REQUIRED_COORDINATES:
        if coordinate_name not in dataset.coords:
            raise WindDataError(f"Required coordinate '{coordinate_name}' is missing.")
        if dataset[coordinate_name].ndim != 1:
            raise WindDataError(
                f"Coordinate '{coordinate_name}' must be one-dimensional; "
                f"received {dataset[coordinate_name].ndim} dimensions."
            )

    _validate_monotonic(dataset["latitude"], "latitude", allow_decreasing=True)
    _validate_monotonic(dataset["longitude"], "longitude", allow_decreasing=True)
    _validate_monotonic(dataset["time"], "time", allow_decreasing=False)

    if bool(((dataset["latitude"] < -90) | (dataset["latitude"] > 90)).any()):
        raise WindDataError("Latitude values must be within the range -90 to 90.")
    if bool(((dataset["longitude"] < -180) | (dataset["longitude"] > 360)).any()):
        raise WindDataError("Longitude values must be within the range -180 to 360.")

    for variable_name in _REQUIRED_VARIABLES:
        wind = dataset[variable_name]
        missing_dimensions = set(_OUTPUT_DIMENSIONS) - set(wind.dims)
        if missing_dimensions:
            names = ", ".join(sorted(missing_dimensions))
            raise WindDataError(
                f"Wind variable '{variable_name}' is missing required dimension(s): "
                f"{names}."
            )
        unexpected_dimensions = set(wind.dims) - set(_OUTPUT_DIMENSIONS)
        if unexpected_dimensions:
            names = ", ".join(sorted(unexpected_dimensions))
            raise WindDataError(
                f"Wind variable '{variable_name}' has unsupported dimension(s): "
                f"{names}."
            )
        _validate_wind_units(wind, variable_name)


def _validate_monotonic(
    coordinate: xr.DataArray, name: str, *, allow_decreasing: bool
) -> None:
    """Ensure a coordinate is monotonic in its permitted direction."""
    index = coordinate.to_index()
    is_valid = index.is_monotonic_increasing or (
        allow_decreasing and index.is_monotonic_decreasing
    )
    if not is_valid:
        direction = "monotonic" if allow_decreasing else "monotonically increasing"
        raise WindDataError(f"Coordinate '{name}' must be {direction}.")


def _validate_wind_units(wind: xr.DataArray, variable_name: str) -> None:
    """Ensure a wind variable declares a supported metres-per-second unit."""
    units = wind.attrs.get("units")
    normalized_units = str(units).strip().lower() if units is not None else None
    if normalized_units not in _ACCEPTED_WIND_UNITS:
        raise WindDataError(
            f"Wind variable '{variable_name}' must use metres-per-second units "
            f"(for example 'm s-1'); received {units!r}."
        )
