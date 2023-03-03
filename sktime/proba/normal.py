# -*- coding: utf-8 -*-
# copyright: sktime developers, BSD-3-Clause License (see LICENSE file)
"""Normal/Gaussian probability distribution."""

__author__ = ["fkiraly"]

import numpy as np
import pandas as pd

from scipy.special import erf, erfinv

from sktime.proba.base import BaseDistribution


class Normal(BaseDistribution):
    """Normal distribution (sktime native).

    Parameters
    ----------
    mean : float or array of float (1D or 2D)
        mean of the normal distribution
    sd : float or array of float (1D or 2D), must be positive
        standard deviation of the normal distribution
    index : pd.Index, optional, default = RangeIndex
    columns : pd.Index, optional, default = RangeIndex

    Example
    -------
    >>> from sktime.proba.normal import Normal

    >>> n = Normal(mu=[[0, 1], [2, 3], [4, 5]], sigma=1)
    """

    _tags = {}

    def __init__(self, mu, sigma, index=None, columns=None):

        self.mu = mu
        self.sigma = sigma

        self._mu, self._sigma = self._get_bc_params()
        shape = self._mu.shape

        if index is None:
            index = pd.RangeIndex(shape[0])

        if columns is None:
            columns = pd.RangeIndex(shape[1])

        super(Normal, self).__init__(index=index, columns=columns)

    def _get_bc_params(self):
        return np.broadcast_arrays(self.mu, self.sigma)

    def energy(self, x=None):
        """Energy of self, w.r.t. self or a constant frame x."""
        # note: self-energy, x=None case seems correct
        if x is None:
            sd_arr = self._sigma
            energy_arr = 2 * np.sum(sd_arr, axis=1) / np.sqrt(np.pi)
            energy = pd.DataFrame(energy_arr, index=self.index, columns=["energy"])
        else:
            mu_arr, sd_arr = self._mu, self._sigma
            c_arr = (x - mu_arr) * (2 * self.cdf(x) - 1) + 2 * sd_arr**2 * self.pdf(x)
            energy_arr = np.sum(c_arr, axis=1)
            energy = pd.DataFrame(energy_arr, index=self.index, columns=["energy"])
        return energy

    def mean(self):
        """Return expected value of the distribution."""
        mean_arr = self._mu
        return pd.DataFrame(mean_arr, index=self.index, columns=self.columns)

    def var(self):
        """Return element/entry-wise variance of the distribution."""
        sd_arr = self._sigma
        return pd.DataFrame(sd_arr, index=self.index, columns=self.columns) ** 2

    def pdf(self, x):
        """Probability density function."""
        d = self.loc[x.index, x.columns]
        pdf_arr = np.exp(-0.5 * ((x.values - d.mu) / d.sigma)**2)
        pdf_arr = pdf_arr / (d.sigma * np.sqrt(2 * np.pi))
        return pd.DataFrame(pdf_arr, index=x.index, columns=x.columns)

    def log_pdf(self, x):
        """Logarithmic probability density function."""
        d = self.loc[x.index, x.columns]
        lpdf_arr = -0.5 * ((x.values - d.mu) / d.sigma)**2
        lpdf_arr = lpdf_arr - np.log(d.sigma * np.sqrt(2 * np.pi))
        return pd.DataFrame(lpdf_arr, index=x.index, columns=x.columns)

    def cdf(self, x):
        """Cumulative distribution function."""
        d = self.loc[x.index, x.columns]
        cdf_arr = 0.5 + 0.5 * erf((x.values - d.mu) / (d.sigma * np.sqrt(2)))
        return pd.DataFrame(cdf_arr, index=x.index, columns=x.columns)

    def ppf(self, p):
        """Quantile function = percent point function = inverse cdf."""
        d = self.loc[p.index, p.columns]
        icdf_arr = d.mu + d.sigma * np.sqrt(2) * erfinv(2 * p.values - 1)
        return pd.DataFrame(icdf_arr, index=p.index, columns=p.columns)

    def sample(self, n_samples=None):
        """Sample from the distribution.

        Parameters
        ----------
        n_samples : int, optional, default = None

        Returns
        -------
        if `n_samples` is `None`:
        returns a sample that contains a single sample from `self`,
        in `pd.DataFrame` mtype format convention, with `index` and `columns` as `self`
        if n_samples is `int`:
        returns a `pd.DataFrame` that contains `n_samples` i.i.d. samples from `self`,
        in `pd-multiindex` mtype format convention, with same `columns` as `self`,
        and `MultiIndex` that is product of `RangeIndex(n_samples)` and `self.index`
        """
        def gen_unif():
            np_unif = np.random.uniform(size=self.shape)
            return pd.DataFrame(np_unif, index=self.index, columns=self.columns)

        if n_samples is None:
            return self.ppf(gen_unif())
        else:
            pd_smpl = [self.ppf(gen_unif()) for _ in range(n_samples)]
            df_spl = pd.concat(pd_smpl, keys=range(n_samples))
            return df_spl

    @classmethod
    def get_test_params(cls, parameter_set="default"):
        """Return testing parameter settings for the estimator."""
        params1 = {"mu": [[0, 1], [2, 3], [4, 5]], "sigma": 1}
        params2 = {
            "mu": 0,
            "sigma": 1,
            "index": pd.Index([1, 2, 5]),
            "columns": pd.Index(["a", "b"]),
        }
        return [params1, params2]