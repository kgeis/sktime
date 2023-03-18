# -*- coding: utf-8 -*-
"""Tests for BaseForecaster API points.

# copyright: sktime developers, BSD-3-Clause License (see LICENSE file)
"""

__author__ = ["mloning", "kejsitake", "fkiraly"]

import numpy as np
import pandas as pd
import pytest

from sktime.datatypes import check_is_mtype
from sktime.datatypes._utilities import get_cutoff
from sktime.exceptions import NotFittedError
from sktime.forecasting.base._delegate import _DelegatedForecaster
from sktime.forecasting.model_selection import (
    ExpandingWindowSplitter,
    SlidingWindowSplitter,
    temporal_train_test_split,
)
from sktime.forecasting.tests._config import (
    TEST_ALPHAS,
    TEST_FHS,
    TEST_OOS_FHS,
    TEST_STEP_LENGTHS_INT,
    TEST_WINDOW_LENGTHS_INT,
    VALID_INDEX_FH_COMBINATIONS,
)
from sktime.performance_metrics.forecasting import mean_absolute_percentage_error
from sktime.tests.test_all_estimators import BaseFixtureGenerator, QuickTester
from sktime.utils._testing.forecasting import (
    _assert_correct_columns,
    _assert_correct_pred_time_index,
    _get_expected_index_for_update_predict,
    _get_n_columns,
    _make_fh,
    make_forecasting_problem,
)
from sktime.utils._testing.series import _make_series
from sktime.utils.validation.forecasting import check_fh

# get all forecasters
FH0 = 1
INVALID_X_INPUT_TYPES = [list("foo"), tuple()]
INVALID_y_INPUT_TYPES = [list("bar"), tuple()]

# testing data
y = make_forecasting_problem()
y_train, y_test = temporal_train_test_split(y, train_size=0.75)

# names for index/fh combinations to display in tests
index_fh_comb_names = [f"{x[0]}-{x[1]}-{x[2]}" for x in VALID_INDEX_FH_COMBINATIONS]

pytest_skip_msg = (
    "ForecastingHorizon with timedelta values "
    "is currently experimental and not supported everywhere"
)


class ForecasterFixtureGenerator(BaseFixtureGenerator):
    """Fixture generator for forecasting tests.

    Fixtures parameterized
    ----------------------
    estimator_class: estimator inheriting from BaseObject
        ranges over all estimator classes not excluded by EXCLUDED_TESTS
    estimator_instance: instance of estimator inheriting from BaseObject
        ranges over all estimator classes not excluded by EXCLUDED_TESTS
        instances are generated by create_test_instance class method
    scenario: instance of TestScenario
        ranges over all scenarios returned by retrieve_scenarios
    """

    # note: this should be separate from TestAllForecasters
    #   additional fixtures, parameters, etc should be added here
    #   TestAllForecasters should contain the tests only

    estimator_type_filter = "forecaster"

    fixture_sequence = [
        "estimator_class",
        "estimator_instance",
        "n_columns",
        "scenario",
        # "fh",
        "update_params",
        "step_length",
    ]

    def _generate_n_columns(self, test_name, **kwargs):
        """Return number of columns for series generation in positive test cases.

        Fixtures parameterized
        ----------------------
        n_columns: int
            1 for univariate forecasters, 2 for multivariate forecasters
            ranges over 1 and 2 for forecasters which are both uni/multivariate
        """
        if "estimator_class" in kwargs.keys():
            scitype_tag = kwargs["estimator_class"].get_class_tag("scitype:y")
        elif "estimator_instance" in kwargs.keys():
            scitype_tag = kwargs["estimator_instance"].get_tag("scitype:y")
        else:
            return []

        n_columns_list = _get_n_columns(scitype_tag)
        if len(n_columns_list) == 1:
            n_columns_names = ["" for x in n_columns_list]
        else:
            n_columns_names = [f"y:{x}cols" for x in n_columns_list]

        return n_columns_list, n_columns_names

    def _generate_update_params(self, test_name, **kwargs):
        """Return update_params for update calls.

        Fixtures parameterized
        ----------------------
        update_params: bool
            whether to update parameters in update; ranges over True, False
        """
        return [True, False], ["update_params=True", "update_params=False"]

    def _generate_step_length(self, test_name, **kwargs):
        """Return step length for window.

        Fixtures parameterized
        ----------------------
        step_length: int
            1 if update_params=True; TEST_STEP_LENGTH_INT if update_params=False
        """
        update_params = kwargs["update_params"]
        if update_params:
            return [1], [""]
        else:
            return TEST_STEP_LENGTHS_INT, [f"step={a}" for a in TEST_STEP_LENGTHS_INT]


class TestAllForecasters(ForecasterFixtureGenerator, QuickTester):
    """Module level tests for all sktime forecasters."""

    def test_get_fitted_params(self, estimator_instance, scenario):
        """Test get_fitted_params."""
        scenario.run(estimator_instance, method_sequence=["fit"])
        try:
            params = estimator_instance.get_fitted_params()
            assert isinstance(params, dict)

        except NotImplementedError:
            pass

    # todo: should these not be checked in test_all_estimators?
    def test_raises_not_fitted_error(self, estimator_instance):
        """Test that calling post-fit methods before fit raises error."""
        # We here check extra method of the forecaster API: update and update_predict.
        with pytest.raises(NotFittedError):
            estimator_instance.update(y_test, update_params=False)

        with pytest.raises(NotFittedError):
            cv = SlidingWindowSplitter(fh=1, window_length=1, start_with_window=False)
            estimator_instance.update_predict(y_test, cv=cv)

        try:
            with pytest.raises(NotFittedError):
                estimator_instance.get_fitted_params()
        except NotImplementedError:
            pass

    def test_y_multivariate_raises_error(self, estimator_instance):
        """Test that wrong y scitype raises error (uni/multivariate not supported)."""
        if estimator_instance.get_tag("scitype:y") == "multivariate":
            y = _make_series(n_columns=1)
            with pytest.raises(ValueError, match=r"two or more variables"):
                estimator_instance.fit(y, fh=FH0)

        if estimator_instance.get_tag("scitype:y") in ["univariate", "both"]:
            # this should pass since "both" allows any number of variables
            # and "univariate" automatically vectorizes, behaves multivariate
            pass

    # todo: should these not be "negative scenarios", tested in test_all_estimators?
    @pytest.mark.parametrize("y", INVALID_y_INPUT_TYPES)
    def test_y_invalid_type_raises_error(self, estimator_instance, y):
        """Test that invalid y input types raise error."""
        with pytest.raises(TypeError, match=r"type"):
            estimator_instance.fit(y, fh=FH0)

    # todo: should these not be "negative scenarios", tested in test_all_estimators?
    @pytest.mark.parametrize("X", INVALID_X_INPUT_TYPES)
    def test_X_invalid_type_raises_error(self, estimator_instance, n_columns, X):
        """Test that invalid X input types raise error."""
        y_train = _make_series(n_columns=n_columns)
        try:
            with pytest.raises(TypeError, match=r"type"):
                estimator_instance.fit(y_train, X, fh=FH0)
        except NotImplementedError as e:
            msg = str(e).lower()
            assert "exogenous" in msg

    # todo: refactor with scenarios. Need to override fh and scenario args for this.
    @pytest.mark.parametrize(
        "index_fh_comb", VALID_INDEX_FH_COMBINATIONS, ids=index_fh_comb_names
    )
    @pytest.mark.parametrize("fh_int", TEST_FHS, ids=[f"fh={fh}" for fh in TEST_FHS])
    def test_predict_time_index(
        self, estimator_instance, n_columns, index_fh_comb, fh_int
    ):
        """Check that predicted time index matches forecasting horizon.

        Tests predicted time index for predict and predict_residuals.
        """
        index_type, fh_type, is_relative = index_fh_comb
        if fh_type == "timedelta":
            return None
            # todo: ensure check_estimator works with pytest.skip like below
            # pytest.skip(
            #    "ForecastingHorizon with timedelta values "
            #     "is currently experimental and not supported everywhere"
            # )
        y_train = _make_series(
            n_columns=n_columns, index_type=index_type, n_timepoints=50
        )
        cutoff = get_cutoff(y_train, return_index=True)
        fh = _make_fh(cutoff, fh_int, fh_type, is_relative)

        try:
            estimator_instance.fit(y_train, fh=fh)
            y_pred = estimator_instance.predict()
            _assert_correct_pred_time_index(y_pred.index, cutoff, fh=fh_int)
            _assert_correct_columns(y_pred, y_train)

            y_test = _make_series(
                n_columns=n_columns, index_type=index_type, n_timepoints=len(y_pred)
            )
            y_test.index = y_pred.index
            y_res = estimator_instance.predict_residuals(y_test)
            _assert_correct_pred_time_index(y_res.index, cutoff, fh=fh)
        except NotImplementedError:
            pass

    @pytest.mark.parametrize(
        "index_fh_comb", VALID_INDEX_FH_COMBINATIONS, ids=index_fh_comb_names
    )
    @pytest.mark.parametrize(
        "fh_int_oos", TEST_OOS_FHS, ids=[f"fh={fh}" for fh in TEST_OOS_FHS]
    )
    def test_predict_time_index_with_X(
        self, estimator_instance, n_columns, index_fh_comb, fh_int_oos
    ):
        """Check that predicted time index matches forecasting horizon."""
        index_type, fh_type, is_relative = index_fh_comb
        if fh_type == "timedelta":
            return None
            # todo: ensure check_estimator works with pytest.skip like below
            # pytest.skip(
            #    "ForecastingHorizon with timedelta values "
            #     "is currently experimental and not supported everywhere"
            # )
        z, X = make_forecasting_problem(index_type=index_type, make_X=True)

        # Some estimators may not support all time index types and fh types, hence we
        # need to catch NotImplementedErrors.
        y = _make_series(n_columns=n_columns, index_type=index_type)
        cutoff = get_cutoff(y.iloc[: len(y) // 2], return_index=True)
        fh = _make_fh(cutoff, fh_int_oos, fh_type, is_relative)

        y_train, _, X_train, X_test = temporal_train_test_split(y, X, fh=fh)

        try:
            estimator_instance.fit(y_train, X_train, fh=fh)
            y_pred = estimator_instance.predict(X=X_test)
            cutoff = get_cutoff(y_train, return_index=True)
            _assert_correct_pred_time_index(y_pred.index, cutoff, fh)
            _assert_correct_columns(y_pred, y_train)
        except NotImplementedError:
            pass

    @pytest.mark.parametrize(
        "index_fh_comb", VALID_INDEX_FH_COMBINATIONS, ids=index_fh_comb_names
    )
    def test_predict_time_index_in_sample_full(
        self, estimator_instance, n_columns, index_fh_comb
    ):
        """Check that predicted time index equals fh for full in-sample predictions."""
        index_type, fh_type, is_relative = index_fh_comb
        if fh_type == "timedelta":
            return None
            # todo: ensure check_estimator works with pytest.skip like below
            # pytest.skip(
            #    "ForecastingHorizon with timedelta values "
            #     "is currently experimental and not supported everywhere"
            # )
        y_train = _make_series(n_columns=n_columns, index_type=index_type)
        cutoff = get_cutoff(y_train, return_index=True)
        steps = -np.arange(len(y_train))
        fh = _make_fh(cutoff, steps, fh_type, is_relative)

        try:
            estimator_instance.fit(y_train, fh=fh)
            y_pred = estimator_instance.predict()
            _assert_correct_pred_time_index(y_pred.index, cutoff, fh)
        except NotImplementedError:
            pass

    def test_predict_series_name_preserved(self, estimator_instance):
        """Test that fit/predict preserves name attribute and type of pd.Series."""
        # skip this test if estimator needs multivariate data
        # because then it does not take pd.Series at all
        if estimator_instance.get_tag("scitype:y") == "multivariate":
            return None

        y_train = _make_series(n_timepoints=15)
        y_train.name = "foo"

        estimator_instance.fit(y_train, fh=[1, 2, 3])
        y_pred = estimator_instance.predict()

        _assert_correct_columns(y_pred, y_train)

    def _check_pred_ints(
        self, pred_ints: pd.DataFrame, y_train: pd.Series, y_pred: pd.Series, fh_int
    ):
        # make iterable
        if isinstance(pred_ints, pd.DataFrame):
            pred_ints = [pred_ints]

        for pred_int in pred_ints:
            # check column naming convention
            assert list(pred_int.columns) == ["lower", "upper"]

            # check time index
            cutoff = get_cutoff(y_train, return_index=True)
            _assert_correct_pred_time_index(pred_int.index, cutoff, fh_int)
            # check values
            assert np.all(pred_int["upper"] >= pred_int["lower"])

            # check if errors are weakly monotonically increasing
            # pred_errors = y_pred - pred_int["lower"]
            # # assert pred_errors.is_mononotic_increasing
            # assert np.all(
            #     pred_errors.values[1:].round(4) >= pred_errors.values[:-1].round(4)
            # )

    @pytest.mark.parametrize("index_type", [None, "range"])
    @pytest.mark.parametrize(
        "coverage", TEST_ALPHAS, ids=[f"alpha={a}" for a in TEST_ALPHAS]
    )
    @pytest.mark.parametrize(
        "fh_int_oos", TEST_OOS_FHS, ids=[f"fh={fh}" for fh in TEST_OOS_FHS]
    )
    def test_predict_interval(
        self, estimator_instance, n_columns, index_type, fh_int_oos, coverage
    ):
        """Check prediction intervals returned by predict_interval.

        Arguments
        ---------
        estimator_instance : BaseEstimator class descendant instance, forecaster to test
        n_columns : number of columns for the test data
        index_type : index type of the test data
        fh_int_oos : forecasting horizon to test the forecaster at, all out of sample
        coverage: float, coverage at which to make prediction intervals

        Raises
        ------
        AssertionError - if Forecaster test instance has "capability:pred_int"
                and pred. int are not returned correctly when calling predict_interval
        AssertionError - if Forecaster test instance does not have "capability:pred_int"
                and no NotImplementedError is raised when calling predict_interval
        """
        y_train = _make_series(n_columns=n_columns, index_type=index_type)
        estimator_instance.fit(y_train, fh=fh_int_oos)
        if estimator_instance.get_tag("capability:pred_int"):

            pred_ints = estimator_instance.predict_interval(
                fh_int_oos, coverage=coverage
            )
            valid, msg, _ = check_is_mtype(
                pred_ints, mtype="pred_interval", scitype="Proba", return_metadata=True
            )  # type: ignore
            assert valid, msg

        else:
            with pytest.raises(NotImplementedError, match="prediction intervals"):
                estimator_instance.predict_interval(fh_int_oos, coverage=coverage)

    def _check_predict_quantiles(
        self, pred_quantiles: pd.DataFrame, y_train: pd.Series, fh, alpha
    ):
        # check if the input is a dataframe
        assert isinstance(pred_quantiles, pd.DataFrame)
        # check time index (also checks forecasting horizon is more than one element)
        cutoff = get_cutoff(y_train, return_index=True)
        _assert_correct_pred_time_index(pred_quantiles.index, cutoff, fh)
        # Forecasters where name of variables do not exist
        # In this cases y_train is series - the upper level in dataframe == 'Quantiles'
        if isinstance(y_train, pd.Series):
            expected = pd.MultiIndex.from_product([["Quantiles"], [alpha]])
        else:
            # multiply variables with all alpha values
            expected = pd.MultiIndex.from_product([y_train.columns, [alpha]])
        found = pred_quantiles.columns.to_flat_index()
        assert all(expected == found)

        if isinstance(alpha, list):
            # sorts the columns that correspond to alpha values
            pred_quantiles = pred_quantiles.reindex(
                columns=pred_quantiles.columns.reindex(sorted(alpha), level=1)[0]
            )

            # check if values are monotonically increasing
            for var in pred_quantiles.columns.levels[0]:
                for index in range(len(pred_quantiles.index)):
                    assert pred_quantiles[var].iloc[index].is_monotonic_increasing

    @pytest.mark.parametrize(
        "alpha", TEST_ALPHAS, ids=[f"alpha={a}" for a in TEST_ALPHAS]
    )
    @pytest.mark.parametrize(
        "fh_int_oos", TEST_OOS_FHS, ids=[f"fh={fh}" for fh in TEST_OOS_FHS]
    )
    def test_predict_quantiles(self, estimator_instance, n_columns, fh_int_oos, alpha):
        """Check prediction quantiles returned by predict_quantiles.

        Arguments
        ---------
        Forecaster: BaseEstimator class descendant, forecaster to test
        fh: ForecastingHorizon, fh at which to test prediction
        alpha: float, alpha at which to make prediction intervals

        Raises
        ------
        AssertionError - if Forecaster test instance has "capability:pred_int"
                and pred. int are not returned correctly when calling predict_quantiles
        AssertionError - if Forecaster test instance does not have "capability:pred_int"
                and no NotImplementedError is raised when calling predict_quantiles
        """
        y_train = _make_series(n_columns=n_columns)
        estimator_instance.fit(y_train, fh=fh_int_oos)
        if estimator_instance.get_tag("capability:pred_int"):
            quantiles = estimator_instance.predict_quantiles(fh=fh_int_oos, alpha=alpha)
            self._check_predict_quantiles(quantiles, y_train, fh_int_oos, alpha)
        else:
            with pytest.raises(NotImplementedError, match="quantile predictions"):
                estimator_instance.predict_quantiles(fh=fh_int_oos, alpha=alpha)

    def _check_predict_proba(self, pred_dist, y_train, fh_int):
        from sktime.proba.base import BaseDistribution

        assert isinstance(pred_dist, BaseDistribution)
        pred_cols = pred_dist.columns
        pred_index = pred_dist.index

        # check time index
        cutoff = get_cutoff(y_train, return_index=True)
        _assert_correct_pred_time_index(pred_index, cutoff, fh_int)

        # check columns
        if isinstance(y_train, pd.Series):
            assert (pred_cols == pd.Index([0])).all()
        else:
            assert (pred_cols == y_train.index).all()

    # todo 0.18.0 or 0.19.0: remove legacy_interface parameter below
    @pytest.mark.parametrize(
        "fh_int_oos", TEST_OOS_FHS, ids=[f"fh={fh}" for fh in TEST_OOS_FHS]
    )
    def test_predict_proba(self, estimator_instance, n_columns, fh_int_oos):
        """Check predictive distribution returned by predict_proba.

        Arguments
        ---------
        Forecaster: BaseEstimator class descendant, forecaster to test
        fh: ForecastingHorizon, fh at which to test prediction

        Raises
        ------
        AssertionError - if Forecaster test instance has "capability:pred_int"
                and pred. int are not returned correctly when calling predict_proba
        AssertionError - if Forecaster test instance does not have "capability:pred_int"
                and no NotImplementedError is raised when calling predict_proba
        """
        y_train = _make_series(n_columns=n_columns)
        estimator_instance.fit(y_train, fh=fh_int_oos)

        if estimator_instance.get_tag("capability:pred_int"):
            try:
                pred_dist = estimator_instance.predict_proba(legacy_interface=False)
                self._check_predict_proba(pred_dist, y_train, fh_int_oos)
            except NotImplementedError:
                pass
        else:
            with pytest.raises(NotImplementedError, match="probabilistic predictions"):
                estimator_instance.predict_proba(legacy_interface=False)

    def test_pred_int_tag(self, estimator_instance):
        """Checks whether the capability:pred_int tag is correctly set.

        Arguments
        ---------
        estimator_instance : instance of BaseForecaster

        Raises
        ------
        ValueError - if capability:pred_int is True, but neither
            predict_interval nor predict_quantiles have implemented content
            this can be by direct implementation of _predict_interval/_predict_quantiles
            or by defaulting to each other and/or _predict_proba
        """
        f = estimator_instance
        # we skip the _DelegatedForecaster, since it implements delegation methods
        #   which may look like the method is implemented, but in fact it is not
        if isinstance(f, _DelegatedForecaster):
            return None

        # check which methods are implemented
        implements_interval = f._has_implementation_of("_predict_interval")
        implements_quantiles = f._has_implementation_of("_predict_quantiles")
        implements_proba = f._has_implementation_of("_predict_proba")

        pred_int_works = implements_interval or implements_quantiles or implements_proba

        if not pred_int_works and f.get_class_tag("capability:pred_int", False):
            raise ValueError(
                f"{type(f).__name__} does not implement probabilistic forecasting, "
                'but "capability:pred_int" flag has been set to True incorrectly. '
                'The flag "capability:pred_int" should instead be set to False.'
            )

        if pred_int_works and not f.get_class_tag("capability:pred_int", False):
            raise ValueError(
                f"{type(f).__name__} does implement probabilistic forecasting, "
                'but "capability:pred_int" flag has been set to False incorrectly. '
                'The flag "capability:pred_int" should instead be set to True.'
            )

    @pytest.mark.parametrize(
        "fh_int_oos", TEST_OOS_FHS, ids=[f"fh={fh}" for fh in TEST_OOS_FHS]
    )
    def test_score(self, estimator_instance, n_columns, fh_int_oos):
        """Check score method."""
        y = _make_series(n_columns=n_columns)
        y_train, y_test = temporal_train_test_split(y)
        estimator_instance.fit(y_train, fh=fh_int_oos)
        y_pred = estimator_instance.predict()

        fh_idx = check_fh(fh_int_oos).to_indexer()  # get zero based index
        expected = mean_absolute_percentage_error(
            y_test.iloc[fh_idx], y_pred, symmetric=False
        )

        # compare expected score with actual score
        actual = estimator_instance.score(y_test.iloc[fh_idx], fh=fh_int_oos)
        assert actual == expected

    @pytest.mark.parametrize(
        "fh_int_oos", TEST_OOS_FHS, ids=[f"fh={fh}" for fh in TEST_OOS_FHS]
    )
    def test_update_predict_single(
        self, estimator_instance, n_columns, fh_int_oos, update_params
    ):
        """Check correct time index of update-predict."""
        y = _make_series(n_columns=n_columns)
        y_train, y_test = temporal_train_test_split(y)
        estimator_instance.fit(y_train, fh=fh_int_oos)
        y_pred = estimator_instance.update_predict_single(
            y_test, update_params=update_params
        )
        cutoff = get_cutoff(y_train, return_index=True)
        _assert_correct_pred_time_index(y_pred.index, cutoff, fh_int_oos)
        _assert_correct_columns(y_pred, y_train)

    @pytest.mark.parametrize(
        "fh_int_oos", TEST_OOS_FHS, ids=[f"fh={fh}" for fh in TEST_OOS_FHS]
    )
    @pytest.mark.parametrize("initial_window", TEST_WINDOW_LENGTHS_INT)
    def test_update_predict_predicted_index(
        self,
        estimator_instance,
        n_columns,
        fh_int_oos,
        step_length,
        initial_window,
        update_params,
    ):
        """Check predicted index in update_predict."""
        y = _make_series(n_columns=n_columns, all_positive=True, index_type="datetime")
        y_train, y_test = temporal_train_test_split(y)
        cv = ExpandingWindowSplitter(
            fh=fh_int_oos,
            initial_window=initial_window,
            step_length=step_length,
        )
        estimator_instance.fit(y_train, fh=fh_int_oos)
        y_pred = estimator_instance.update_predict(
            y_test, cv=cv, update_params=update_params
        )
        assert isinstance(y_pred, (pd.Series, pd.DataFrame))
        expected = _get_expected_index_for_update_predict(
            y_test, fh_int_oos, step_length, initial_window
        )
        actual = y_pred.index
        np.testing.assert_array_equal(actual, expected)

    def test__y_and_cutoff(self, estimator_instance, n_columns):
        """Check cutoff and _y."""
        # check _y and cutoff is None after construction
        f = estimator_instance

        y = _make_series(n_columns=n_columns)
        y_train, y_test = temporal_train_test_split(y, train_size=0.75)

        # check that _y and cutoff are empty when estimator is constructed
        assert f._y is None
        assert f.cutoff is None

        # check that _y and cutoff is updated during fit
        f.fit(y_train, fh=FH0)
        # assert isinstance(f._y, pd.Series)
        # action:uncomments the line above
        # why: fails for multivariates cause they are DataFrames
        # solution: look for a general solution for Series and DataFrames
        assert len(f._y) > 0
        assert f.cutoff == y_train.index[-1]

        # check data pointers
        np.testing.assert_array_equal(f._y.index, y_train.index)

        # check that _y and cutoff is updated during update
        f.update(y_test, update_params=False)
        np.testing.assert_array_equal(
            f._y.index, np.append(y_train.index, y_test.index)
        )
        assert f.cutoff == y_test.index[-1]

    def test__y_when_refitting(self, estimator_instance, n_columns):
        """Test that _y is updated when forecaster is refitted."""
        y_train = _make_series(n_columns=n_columns)
        estimator_instance.fit(y_train, fh=FH0)
        estimator_instance.fit(y_train[3:], fh=FH0)
        # using np.squeeze to make the test flexible to shape differeces like
        # (50,) and (50, 1)
        assert np.all(np.squeeze(estimator_instance._y) == np.squeeze(y_train[3:]))

    def test_fh_attribute(self, estimator_instance, n_columns):
        """Check fh attribute and error handling if two different fh are passed."""
        f = estimator_instance
        y_train = _make_series(n_columns=n_columns)

        f.fit(y_train, fh=FH0)
        np.testing.assert_array_equal(f.fh, FH0)
        f.predict()
        np.testing.assert_array_equal(f.fh, FH0)
        f.predict(FH0)
        np.testing.assert_array_equal(f.fh, FH0)

        # if fh is not required in fit, test this again with fh passed late
        if not f.get_tag("requires-fh-in-fit"):
            f.fit(y_train)
            f.predict(FH0)
            np.testing.assert_array_equal(f.fh, FH0)

    def test_fh_not_passed_error_handling(self, estimator_instance, n_columns):
        """Check that not passing fh in fit/predict raises correct error."""
        f = estimator_instance
        y_train = _make_series(n_columns=n_columns)

        if f.get_tag("requires-fh-in-fit"):
            # if fh required in fit, should raise error if not passed in fit
            with pytest.raises(ValueError):
                f.fit(y_train)
        else:
            # if fh not required in fit, should raise error if not passed until predict
            f.fit(y_train)
            with pytest.raises(ValueError):
                f.predict()

    def test_different_fh_in_fit_and_predict_error_handling(
        self, estimator_instance, n_columns
    ):
        """Check that fh different in fit and predict raises correct error."""
        f = estimator_instance
        # if fh is not required in fit, can be overwritten, should not raise error
        if not f.get_tag("requires-fh-in-fit"):
            return None
        y_train = _make_series(n_columns=n_columns)
        f.fit(y_train, fh=FH0)
        np.testing.assert_array_equal(f.fh, FH0)
        # changing fh during predict should raise error
        with pytest.raises(ValueError):
            f.predict(fh=FH0 + 1)

    def test_hierarchical_with_exogeneous(self, estimator_instance, n_columns):
        """Check that hierarchical forecasting works, also see bug #3961.

        Arguments
        ---------
        estimator_instance : instance of BaseForecaster
        n_columns : number of columns, of the endogeneous data y_train

        Raises
        ------
        Exception - if fit/predict does not complete without error
        AssertionError - if forecast is not expected mtype pd_multiindex_hier,
            and does not have expected row and column indices
        """
        from sktime.datatypes import check_is_mtype
        from sktime.datatypes._utilities import get_window
        from sktime.utils._testing.hierarchical import _make_hierarchical

        y_train = _make_hierarchical(
            hierarchy_levels=(2, 4),
            n_columns=n_columns,
            min_timepoints=22,
            max_timepoints=22,
            index_type="period",
        )
        X = _make_hierarchical(
            hierarchy_levels=(2, 4),
            n_columns=2,
            min_timepoints=24,
            max_timepoints=24,
            index_type="period",
        )
        X.columns = ["foo", "bar"]
        X_train = get_window(X, lag=2)
        X_test = get_window(X, window_length=2)
        fh = [1, 2]

        estimator_instance.fit(y=y_train, X=X_train, fh=fh)
        y_pred = estimator_instance.predict(X=X_test)

        assert isinstance(y_pred, pd.DataFrame)
        assert check_is_mtype(y_pred, "pd_multiindex_hier")
        msg = (
            "returned columns after predict are not as expected. "
            f"expected: {y_train.columns}. Found: {y_pred.columns}"
        )
        assert np.all(y_pred.columns == y_train.columns), msg

        # check consistency of forecast hierarchy with training data
        # some forecasters add __total levels, e.g., ReconcilerForecaster
        # if = not such a forecaster; else = levels are added
        if len(y_pred.index) == len(X_test.index):
            # the indices should be equal iff no levels are added
            assert np.all(y_pred.index == X_test.index)
        else:
            # if levels are added, all expected levels and times should be contained
            assert set(X_test.index).issubset(y_pred.index)
