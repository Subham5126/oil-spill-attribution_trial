"""Tests for loading ERA5 10-m wind data."""

from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from ocean.wind import WindDataError, load_wind


def _wind_dataset(*, time_name: str = "valid_time") -> xr.Dataset:
    """Build a small valid ERA5-like wind dataset."""
    values = np.arange(27, dtype=float).reshape(3, 3, 3)
    return xr.Dataset(
        {
            "u10": ((time_name, "latitude", "longitude"), values, {"units": "m s-1"}),
            "v10": (
                (time_name, "latitude", "longitude"),
                values + 10,
                {"units": "m s-1"},
            ),
            "unrelated": ((time_name,), [1, 2, 3]),
        },
        coords={
            time_name: np.array(
                ["2026-01-01T00", "2026-01-01T01", "2026-01-01T02"],
                dtype="datetime64[h]",
            ),
            "latitude": [25.0, 15.0, 5.0],
            "longitude": [65.0, 72.5, 80.0],
        },
        attrs={"source": "synthetic ERA5 dataset"},
    )


def _write_dataset(tmp_path: Path, dataset: xr.Dataset) -> Path:
    """Write a test dataset to a temporary NetCDF file."""
    path = tmp_path / "wind.nc"
    dataset.to_netcdf(path)
    return path


def test_valid_dataset_loads_successfully(tmp_path: Path) -> None:
    dataset = _wind_dataset()
    loaded = load_wind(_write_dataset(tmp_path, dataset))

    assert loaded.attrs["source"] == "synthetic ERA5 dataset"
    np.testing.assert_array_equal(loaded["u10"].values, dataset["u10"].values)


@pytest.mark.parametrize("variable_name", ["u10", "v10"])
def test_missing_required_wind_variable_raises_clear_error(
    tmp_path: Path, variable_name: str
) -> None:
    dataset = _wind_dataset().drop_vars(variable_name)

    with pytest.raises(WindDataError, match=rf"variable '{variable_name}' is missing"):
        load_wind(_write_dataset(tmp_path, dataset))


def test_missing_time_coordinates_raise_clear_error(tmp_path: Path) -> None:
    dataset = _wind_dataset().drop_vars("valid_time")

    with pytest.raises(WindDataError, match="time coordinate 'time' or 'valid_time' is missing"):
        load_wind(_write_dataset(tmp_path, dataset))


def test_valid_time_is_renamed_to_time(tmp_path: Path) -> None:
    loaded = load_wind(_write_dataset(tmp_path, _wind_dataset()))

    assert "time" in loaded.coords
    assert "valid_time" not in loaded.coords


def test_existing_time_coordinate_is_accepted(tmp_path: Path) -> None:
    loaded = load_wind(_write_dataset(tmp_path, _wind_dataset(time_name="time")))

    assert loaded["u10"].dims == ("time", "latitude", "longitude")


@pytest.mark.parametrize("coordinate_name", ["latitude", "longitude"])
def test_missing_spatial_coordinate_raises_clear_error(
    tmp_path: Path, coordinate_name: str
) -> None:
    dataset = _wind_dataset().drop_vars(coordinate_name)

    with pytest.raises(WindDataError, match=rf"coordinate '{coordinate_name}' is missing"):
        load_wind(_write_dataset(tmp_path, dataset))


@pytest.mark.parametrize(
    ("coordinate_name", "values", "message"),
    [
        ("latitude", [15.0, 5.0, -91.0], "Latitude values must be within"),
        ("longitude", [65.0, 72.5, 361.0], "Longitude values must be within"),
    ],
)
def test_invalid_geographic_coordinate_raises_clear_error(
    tmp_path: Path, coordinate_name: str, values: list[float], message: str
) -> None:
    dataset = _wind_dataset().assign_coords({coordinate_name: values})

    with pytest.raises(WindDataError, match=message):
        load_wind(_write_dataset(tmp_path, dataset))


@pytest.mark.parametrize(
    ("coordinate_name", "values"),
    [
        ("latitude", [25.0, 5.0, 15.0]),
        ("longitude", [65.0, 80.0, 72.5]),
        (
            "valid_time",
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
    dataset = _wind_dataset().assign_coords({coordinate_name: values})

    with pytest.raises(WindDataError, match=rf"Coordinate '.+' must be"):
        load_wind(_write_dataset(tmp_path, dataset))


def test_invalid_wind_units_raise_clear_error(tmp_path: Path) -> None:
    dataset = _wind_dataset()
    dataset["u10"].attrs["units"] = "knots"

    with pytest.raises(WindDataError, match="'u10' must use metres-per-second units"):
        load_wind(_write_dataset(tmp_path, dataset))


def test_missing_wind_units_raise_clear_error(tmp_path: Path) -> None:
    dataset = _wind_dataset()
    del dataset["v10"].attrs["units"]

    with pytest.raises(WindDataError, match="'v10' must use metres-per-second units"):
        load_wind(_write_dataset(tmp_path, dataset))


def test_output_is_limited_to_standardized_wind_variables(tmp_path: Path) -> None:
    loaded = load_wind(_write_dataset(tmp_path, _wind_dataset()))

    assert set(loaded.data_vars) == {"u10", "v10"}
    assert loaded["u10"].dims == ("time", "latitude", "longitude")
    assert loaded["v10"].dims == ("time", "latitude", "longitude")
    assert loaded["u10"].attrs["units"] == "m/s"
    assert loaded["v10"].attrs["units"] == "m/s"


def test_sample_era5_dataset_loads_when_available() -> None:
    sample_path = Path("data/sample/era5/wind_test.nc")
    if not sample_path.is_file():
        pytest.skip("ERA5 sample NetCDF is not available in this checkout.")

    loaded = load_wind(sample_path)

    assert set(loaded.data_vars) == {"u10", "v10"}
    assert loaded["u10"].dims == ("time", "latitude", "longitude")
    assert loaded["v10"].dims == ("time", "latitude", "longitude")
