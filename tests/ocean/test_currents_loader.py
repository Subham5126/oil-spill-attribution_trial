"""Tests for loading Copernicus Marine surface-current data."""

from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from ocean.currents import CurrentDataError, load_currents


def _current_dataset(*, depth: list[float] | None = None) -> xr.Dataset:
    """Build a small valid current dataset, optionally with depth levels."""
    coordinates: dict[str, object] = {
        "time": np.array(
            ["2026-01-01T00", "2026-01-01T01", "2026-01-01T02"],
            dtype="datetime64[h]",
        ),
        "latitude": [18.0, 18.5, 19.0],
        "longitude": [72.0, 72.5, 73.0],
    }
    dimensions = ("time", "latitude", "longitude")
    shape = (3, 3, 3)
    if depth is not None:
        coordinates["depth"] = depth
        dimensions = ("time", "depth", "latitude", "longitude")
        shape = (3, len(depth), 3, 3)

    values = np.arange(np.prod(shape), dtype=float).reshape(shape)
    return xr.Dataset(
        {
            "uo": (dimensions, values, {"units": "m s-1"}),
            "vo": (dimensions, values + 10, {"units": "m s-1"}),
            "unrelated": (("time",), [1, 2, 3]),
        },
        coords=coordinates,
        attrs={"source": "synthetic Copernicus dataset"},
    )


def _write_dataset(tmp_path: Path, dataset: xr.Dataset) -> Path:
    """Write a test dataset to a temporary NetCDF file."""
    path = tmp_path / "currents.nc"
    dataset.to_netcdf(path)
    return path


def test_valid_dataset_loads_successfully(tmp_path: Path) -> None:
    loaded = load_currents(_write_dataset(tmp_path, _current_dataset()))

    assert loaded.attrs["source"] == "synthetic Copernicus dataset"
    np.testing.assert_array_equal(loaded["uo"].values, _current_dataset()["uo"].values)


@pytest.mark.parametrize("variable_name", ["uo", "vo"])
def test_missing_required_velocity_variable_raises_clear_error(
    tmp_path: Path, variable_name: str
) -> None:
    dataset = _current_dataset().drop_vars(variable_name)

    with pytest.raises(CurrentDataError, match=rf"variable '{variable_name}' is missing"):
        load_currents(_write_dataset(tmp_path, dataset))


def test_missing_required_coordinate_raises_clear_error(tmp_path: Path) -> None:
    dataset = _current_dataset().drop_vars("latitude")

    with pytest.raises(CurrentDataError, match="coordinate 'latitude' is missing"):
        load_currents(_write_dataset(tmp_path, dataset))


@pytest.mark.parametrize(
    ("coordinate_name", "values", "message"),
    [
        ("latitude", [-91.0, 18.5, 19.0], "Latitude values must be within"),
        ("longitude", [72.0, 72.5, 361.0], "Longitude values must be within"),
    ],
)
def test_invalid_geographic_coordinate_raises_clear_error(
    tmp_path: Path, coordinate_name: str, values: list[float], message: str
) -> None:
    dataset = _current_dataset().assign_coords({coordinate_name: values})

    with pytest.raises(CurrentDataError, match=message):
        load_currents(_write_dataset(tmp_path, dataset))


@pytest.mark.parametrize(
    ("coordinate_name", "values"),
    [
        ("latitude", [18.0, 19.0, 18.5]),
        ("longitude", [72.0, 73.0, 72.5]),
        (
            "time",
            np.array(
                ["2026-01-01T00", "2026-01-01T02", "2026-01-01T01"],
                dtype="datetime64[h]",
            ),
        ),
    ],
)
def test_non_monotonic_coordinate_raises_clear_error(
    tmp_path: Path, coordinate_name: str, values: object
) -> None:
    dataset = _current_dataset().assign_coords({coordinate_name: values})

    with pytest.raises(CurrentDataError, match=rf"Coordinate '{coordinate_name}' must be"):
        load_currents(_write_dataset(tmp_path, dataset))


def test_invalid_velocity_units_raise_clear_error(tmp_path: Path) -> None:
    dataset = _current_dataset()
    dataset["uo"].attrs["units"] = "knots"

    with pytest.raises(CurrentDataError, match="'uo' must use metres-per-second units"):
        load_currents(_write_dataset(tmp_path, dataset))


def test_singleton_depth_is_removed(tmp_path: Path) -> None:
    loaded = load_currents(_write_dataset(tmp_path, _current_dataset(depth=[0.0])))

    assert "depth" not in loaded.dims
    assert loaded["uo"].dims == ("time", "latitude", "longitude")


def test_multiple_depth_levels_are_rejected(tmp_path: Path) -> None:
    dataset = _current_dataset(depth=[0.0, 10.0])

    with pytest.raises(CurrentDataError, match="singleton surface 'depth' dimension"):
        load_currents(_write_dataset(tmp_path, dataset))


def test_output_is_limited_to_standardized_current_variables(tmp_path: Path) -> None:
    loaded = load_currents(_write_dataset(tmp_path, _current_dataset()))

    assert set(loaded.data_vars) == {"uo", "vo"}
    assert loaded["uo"].dims == ("time", "latitude", "longitude")
    assert loaded["vo"].dims == ("time", "latitude", "longitude")
    assert loaded["uo"].attrs["units"] == "m/s"
    assert loaded["vo"].attrs["units"] == "m/s"


def test_sample_copernicus_dataset_loads_when_available() -> None:
    sample_path = Path("data/sample/copernicus/current_test.nc")
    if not sample_path.is_file():
        pytest.skip("Copernicus sample NetCDF is not available in this checkout.")

    loaded = load_currents(sample_path)

    assert set(loaded.data_vars) == {"uo", "vo"}
    assert loaded["uo"].dims == ("time", "latitude", "longitude")
    assert loaded["vo"].dims == ("time", "latitude", "longitude")
