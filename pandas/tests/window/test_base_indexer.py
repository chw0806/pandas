import numpy as np
import pytest

from pandas import DataFrame, Series
import pandas._testing as tm
from pandas.api.indexers import BaseIndexer, FixedForwardWindowIndexer
from pandas.core.window.indexers import ExpandingIndexer


def test_bad_get_window_bounds_signature():
    class BadIndexer(BaseIndexer):
        def get_window_bounds(self):
            return None

    indexer = BadIndexer()
    with pytest.raises(ValueError, match="BadIndexer does not implement"):
        Series(range(5)).rolling(indexer)


def test_expanding_indexer():
    s = Series(range(10))
    indexer = ExpandingIndexer()
    result = s.rolling(indexer).mean()
    expected = s.expanding().mean()
    tm.assert_series_equal(result, expected)


def test_indexer_constructor_arg():
    # Example found in computation.rst
    use_expanding = [True, False, True, False, True]
    df = DataFrame({"values": range(5)})

    class CustomIndexer(BaseIndexer):
        def get_window_bounds(self, num_values, min_periods, center, closed):
            start = np.empty(num_values, dtype=np.int64)
            end = np.empty(num_values, dtype=np.int64)
            for i in range(num_values):
                if self.use_expanding[i]:
                    start[i] = 0
                    end[i] = i + 1
                else:
                    start[i] = i
                    end[i] = i + self.window_size
            return start, end

    indexer = CustomIndexer(window_size=1, use_expanding=use_expanding)
    result = df.rolling(indexer).sum()
    expected = DataFrame({"values": [0.0, 1.0, 3.0, 3.0, 10.0]})
    tm.assert_frame_equal(result, expected)


def test_indexer_accepts_rolling_args():
    df = DataFrame({"values": range(5)})

    class CustomIndexer(BaseIndexer):
        def get_window_bounds(self, num_values, min_periods, center, closed):
            start = np.empty(num_values, dtype=np.int64)
            end = np.empty(num_values, dtype=np.int64)
            for i in range(num_values):
                if center and min_periods == 1 and closed == "both" and i == 2:
                    start[i] = 0
                    end[i] = num_values
                else:
                    start[i] = i
                    end[i] = i + self.window_size
            return start, end

    indexer = CustomIndexer(window_size=1)
    result = df.rolling(indexer, center=True, min_periods=1, closed="both").sum()
    expected = DataFrame({"values": [0.0, 1.0, 10.0, 3.0, 4.0]})
    tm.assert_frame_equal(result, expected)


def test_win_type_not_implemented():
    class CustomIndexer(BaseIndexer):
        def get_window_bounds(self, num_values, min_periods, center, closed):
            return np.array([0, 1]), np.array([1, 2])

    df = DataFrame({"values": range(2)})
    indexer = CustomIndexer()
    with pytest.raises(NotImplementedError, match="BaseIndexer subclasses not"):
        df.rolling(indexer, win_type="boxcar")


@pytest.mark.parametrize("func", ["cov", "corr"])
def test_notimplemented_functions(func):
    # GH 32865
    class CustomIndexer(BaseIndexer):
        def get_window_bounds(self, num_values, min_periods, center, closed):
            return np.array([0, 1]), np.array([1, 2])

    df = DataFrame({"values": range(2)})
    indexer = CustomIndexer()
    with pytest.raises(NotImplementedError, match=f"{func} is not supported"):
        getattr(df.rolling(indexer), func)()


@pytest.mark.parametrize("constructor", [Series, DataFrame])
@pytest.mark.parametrize(
    "func,np_func,expected,np_kwargs",
    [
        ("count", len, [3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 2.0, np.nan], {},),
        ("min", np.min, [0.0, 1.0, 2.0, 3.0, 4.0, 6.0, 6.0, 7.0, 8.0, np.nan], {},),
        (
            "max",
            np.max,
            [2.0, 3.0, 4.0, 100.0, 100.0, 100.0, 8.0, 9.0, 9.0, np.nan],
            {},
        ),
        (
            "std",
            np.std,
            [
                1.0,
                1.0,
                1.0,
                55.71654452,
                54.85739087,
                53.9845657,
                1.0,
                1.0,
                0.70710678,
                np.nan,
            ],
            {"ddof": 1},
        ),
        (
            "var",
            np.var,
            [
                1.0,
                1.0,
                1.0,
                3104.333333,
                3009.333333,
                2914.333333,
                1.0,
                1.0,
                0.500000,
                np.nan,
            ],
            {"ddof": 1},
        ),
        (
            "median",
            np.median,
            [1.0, 2.0, 3.0, 4.0, 6.0, 7.0, 7.0, 8.0, 8.5, np.nan],
            {},
        ),
    ],
)
def test_rolling_forward_window(constructor, func, np_func, expected, np_kwargs):
    # GH 32865
    values = np.arange(10)
    values[5] = 100.0

    indexer = FixedForwardWindowIndexer(window_size=3)

    match = "Forward-looking windows can't have center=True"
    with pytest.raises(ValueError, match=match):
        rolling = constructor(values).rolling(window=indexer, center=True)
        result = getattr(rolling, func)()

    match = "Forward-looking windows don't support setting the closed argument"
    with pytest.raises(ValueError, match=match):
        rolling = constructor(values).rolling(window=indexer, closed="right")
        result = getattr(rolling, func)()

    rolling = constructor(values).rolling(window=indexer, min_periods=2)
    result = getattr(rolling, func)()

    # Check that the function output matches the explicitly provided array
    expected = constructor(expected)
    tm.assert_equal(result, expected)

    # Check that the rolling function output matches applying an alternative
    # function to the rolling window object
    expected2 = constructor(rolling.apply(lambda x: np_func(x, **np_kwargs)))
    tm.assert_equal(result, expected2)

    # Check that the function output matches applying an alternative function
    # if min_periods isn't specified
    rolling3 = constructor(values).rolling(window=indexer)
    result3 = getattr(rolling3, func)()
    expected3 = constructor(rolling3.apply(lambda x: np_func(x, **np_kwargs)))
    tm.assert_equal(result3, expected3)


@pytest.mark.parametrize("constructor", [Series, DataFrame])
def test_rolling_forward_skewness(constructor):
    values = np.arange(10)
    values[5] = 100.0

    indexer = FixedForwardWindowIndexer(window_size=5)
    rolling = constructor(values).rolling(window=indexer, min_periods=3)
    result = rolling.skew()

    expected = constructor(
        [
            0.0,
            2.232396,
            2.229508,
            2.228340,
            2.229091,
            2.231989,
            0.0,
            0.0,
            np.nan,
            np.nan,
        ]
    )
    tm.assert_equal(result, expected)
