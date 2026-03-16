import pandas as pd

from backtester_runner import _infer_common_date_range, _infer_dates_if_missing


def _make_df():
    dates = pd.to_datetime(
        ["2020-01-01", "2020-02-01", "2020-03-01", "2020-04-01"]
    )
    return pd.DataFrame(
        {
            "Date": dates,
            "A": [1.0, 1.1, 1.2, 1.3],
            "B": [float("nan"), float("nan"), 2.0, 2.1],
        }
    )


def test_infer_common_date_range_across_assets():
    df = _make_df()
    common_start, common_end = _infer_common_date_range(df, ["A", "B"])
    assert common_start == pd.Timestamp("2020-03-01")
    assert common_end == pd.Timestamp("2020-04-01")


def test_infer_dates_if_missing_uses_selected_assets():
    df = _make_df()
    # Only A is selected -> earliest available date for A
    start_date, end_date = _infer_dates_if_missing(df, [1.0, 0.0], None, None)
    assert start_date == pd.Timestamp("2020-01-01")
    assert end_date == pd.Timestamp("2020-04-01")

    # A and B selected -> common range starts at B's first valid date
    start_date, end_date = _infer_dates_if_missing(df, [0.5, 0.5], None, None)
    assert start_date == pd.Timestamp("2020-03-01")
    assert end_date == pd.Timestamp("2020-04-01")
