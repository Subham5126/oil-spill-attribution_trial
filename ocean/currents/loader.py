"""Validation and loading for Copernicus Marine surface-current data."""

from pathlib import Path

import xarray as xr


_REQUIRED_VARIABLES = ("uo", "vo")
_REQUIRED_COORDINATES = ("time", "latitude", "longitude")
_OUTPUT_DIMENSIONS = ("time", "latitude", "longitude")
_ACCEPTED_VELOCITY_UNITS = {"m/s", "m s-1", "m s^-1", "m s**-1"}


class CurrentDataError(ValueError):
    """Raised when a current dataset cannot be used as surface-current input."""


def load_currents(path: str | Path) -> xr.Dataset:
    """Load validated Copernicus Marine surface-current data into memory.

    The returned dataset contains only eastward (``uo``) and northward (``vo``)
    surface velocities, each ordered as ``(time, latitude, longitude)`` with
    units standardized to ``m/s``. No interpolation, filling, or value changes
    are performed.

    Args:
        path: Path to a NetCDF file containing Copernicus Marine current data.

    Raises:
        FileNotFoundError: If ``path`` does not exist or is not a file.
        CurrentDataError: If the dataset does not satisfy the current-data
            contract.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Current NetCDF file does not exist: {file_path}")

    try:
        with xr.open_dataset(file_path) as source:
            dataset = source.load()
    except (OSError, ValueError) as error:
        raise CurrentDataError(
            f"Unable to open current NetCDF file '{file_path}': {error}"
        ) from error

    _validate_dataset(dataset)
    dataset = _remove_singleton_depth(dataset)
    currents = dataset[list(_REQUIRED_VARIABLES)]

    for variable_name in _REQUIRED_VARIABLES:
        currents[variable_name] = currents[variable_name].transpose(
            *_OUTPUT_DIMENSIONS
        )
        currents[variable_name].attrs["units"] = "m/s"

    return currents


def _validate_dataset(dataset: xr.Dataset) -> None:
    """Validate the structural and physical metadata contract for currents."""
    for variable_name in _REQUIRED_VARIABLES:
        if variable_name not in dataset.data_vars:
            raise CurrentDataError(
                f"Required current variable '{variable_name}' is missing."
            )

    for coordinate_name in _REQUIRED_COORDINATES:
        if coordinate_name not in dataset.coords:
            raise CurrentDataError(f"Required coordinate '{coordinate_name}' is missing.")

    for coordinate_name in _REQUIRED_COORDINATES:
        coordinate = dataset[coordinate_name]
        if coordinate.ndim != 1:
            raise CurrentDataError(
                f"Coordinate '{coordinate_name}' must be one-dimensional; "
                f"received {coordinate.ndim} dimensions."
            )

    _validate_monotonic(dataset["latitude"], "latitude", increasing_or_decreasing=True)
    _validate_monotonic(dataset["longitude"], "longitude", increasing_or_decreasing=True)
    _validate_monotonic(dataset["time"], "time", increasing_or_decreasing=False)

    latitude = dataset["latitude"]
    longitude = dataset["longitude"]
    if bool(((latitude < -90) | (latitude > 90)).any()):
        raise CurrentDataError("Latitude values must be within the range -90 to 90.")
    if bool(((longitude < -180) | (longitude > 360)).any()):
        raise CurrentDataError("Longitude values must be within the range -180 to 360.")

    for variable_name in _REQUIRED_VARIABLES:
        velocity = dataset[variable_name]
        missing_dimensions = set(_OUTPUT_DIMENSIONS) - set(velocity.dims)
        if missing_dimensions:
            names = ", ".join(sorted(missing_dimensions))
            raise CurrentDataError(
                f"Current variable '{variable_name}' is missing required "
                f"dimension(s): {names}."
            )
        unexpected_dimensions = set(velocity.dims) - set(_OUTPUT_DIMENSIONS) - {
            "depth"
        }
        if unexpected_dimensions:
            names = ", ".join(sorted(unexpected_dimensions))
            raise CurrentDataError(
                f"Current variable '{variable_name}' has unsupported dimension(s): "
                f"{names}."
            )
        _validate_velocity_units(velocity, variable_name)

    if "depth" in dataset.sizes and dataset.sizes["depth"] != 1:
        raise CurrentDataError(
            "Only a singleton surface 'depth' dimension is supported; "
            f"received {dataset.sizes['depth']} levels."
        )


def _validate_monotonic(
    coordinate: xr.DataArray, name: str, *, increasing_or_decreasing: bool
) -> None:
    """Ensure a coordinate is monotonic in its permitted direction."""
    index = coordinate.to_index()
    is_valid = (
        index.is_monotonic_increasing or index.is_monotonic_decreasing
        if increasing_or_decreasing
        else index.is_monotonic_increasing
    )
    if not is_valid:
        direction = "monotonic" if increasing_or_decreasing else "monotonically increasing"
        raise CurrentDataError(f"Coordinate '{name}' must be {direction}.")


def _validate_velocity_units(velocity: xr.DataArray, variable_name: str) -> None:
    """Ensure a velocity variable declares a supported metres-per-second unit."""
    units = velocity.attrs.get("units")
    normalized_units = str(units).strip().lower() if units is not None else None
    if normalized_units not in _ACCEPTED_VELOCITY_UNITS:
        raise CurrentDataError(
            f"Current variable '{variable_name}' must use metres-per-second units "
            f"(for example 'm s-1'); received {units!r}."
        )


def _remove_singleton_depth(dataset: xr.Dataset) -> xr.Dataset:
    """Drop a validated singleton depth dimension without altering velocities."""
    if "depth" not in dataset.sizes:
        return dataset

    surface_dataset = dataset.isel(depth=0, drop=True)
    for variable_name in _REQUIRED_VARIABLES:
        unexpected_dimensions = set(surface_dataset[variable_name].dims) - set(
            _OUTPUT_DIMENSIONS
        )
        if unexpected_dimensions:
            names = ", ".join(sorted(unexpected_dimensions))
            raise CurrentDataError(
                f"Current variable '{variable_name}' has unsupported dimension(s): "
                f"{names}."
            )
    return surface_dataset
