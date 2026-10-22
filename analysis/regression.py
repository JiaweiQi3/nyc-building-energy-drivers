"""Regress total site energy use on floor area, building age and grid electricity.

Usage:
    python regression.py            # read from the building_energy MySQL database
    python regression.py --csv      # read data/nyc_ll84_cleaned.csv directly

The database connection is read from MYSQL_USER, MYSQL_PASSWORD, MYSQL_HOST
(default localhost) and MYSQL_PORT (default 3306).

Fits linear, log-linear and polynomial OLS models on z-scored variables, reports
R², adjusted R², AIC and BIC, partial R² of each predictor (grouped for the
polynomial terms) and the building age at which the polynomial model peaks.
Tables are written to results/ and figures to figures/.
"""
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_YEAR = 2022

QUERY = """
SELECT r.record_id, r.building_id, r.largest_use_type AS property_type,
       a.year_built, g.total_gfa, e.electricity_use, t.total_energy_use
FROM Benchmark_Record r
JOIN Housing_Age a ON a.record_id = r.record_id
JOIN Gross_Floor_Area g ON g.record_id = r.record_id
JOIN Electricity_Use e ON e.record_id = r.record_id
JOIN Total_Energy_Use t ON t.record_id = r.record_id
"""


def load_from_mysql():
    from sqlalchemy import create_engine
    url = "mysql+mysqlconnector://{}:{}@{}:{}/building_energy".format(
        os.environ["MYSQL_USER"], os.environ.get("MYSQL_PASSWORD", ""),
        os.environ.get("MYSQL_HOST", "localhost"), os.environ.get("MYSQL_PORT", "3306"))
    return pd.read_sql(QUERY, create_engine(url))


def load_from_csv():
    df = pd.read_csv(ROOT / "data" / "nyc_ll84_cleaned.csv")
    return df.rename(columns={
        "Largest Property Use Type": "property_type",
        "Year Built": "year_built",
        "Total GFA": "total_gfa",
        "Electricity Use - Grid Purchase (kBtu)": "electricity_use",
        "Weather Normalized Site Energy Use (kBtu)": "total_energy_use",
    })


def zscore(x):
    return (x - x.mean()) / x.std()


def ols(y, X):
    return sm.OLS(zscore(y), sm.add_constant(zscore(X))).fit()


def partial_r2(full, reduced):
    return (full.rsquared - reduced.rsquared) / (1 - reduced.rsquared)


def describe(df, X):
    """Summary statistics of the modeling variables and the mix of property types."""
    table = pd.DataFrame({
        "Site energy use (kBtu)": df["total_energy_use"],
        "Total GFA (ft²)": X["GFA"],
        "Age (years)": X["Age"],
        "Grid electricity (kBtu)": X["Electricity"],
    }).describe(percentiles=[0.25, 0.5, 0.75]).T
    table.to_csv(ROOT / "results" / "descriptive_stats.csv")
    print("\n===== Descriptive statistics =====")
    print(table.round(1).to_string())
    print(f"buildings: {df['building_id'].nunique():,}")

    if "property_type" in df:
        counts = df["property_type"].value_counts()
        mix = pd.DataFrame({"records": counts, "share": counts / counts.sum()})
        mix.to_csv(ROOT / "results" / "property_types.csv")
        print("\n===== Largest property use type =====")
        print(mix.head(8).round(3).to_string())


def age_peak(model, X_poly):
    """Age at which the fitted polynomial model peaks, in years."""
    b_age, b_age_sq = model.params["Age"], model.params["Age_sq"]
    return -b_age * X_poly["Age_sq"].std() / (2 * b_age_sq * X_poly["Age"].std())


def age_effect_plot(model, X_poly, y, peak):
    """Predicted site energy use across building age, other predictors at their means."""
    lo, hi = np.percentile(X_poly["Age"], [1, 99])
    age = np.linspace(lo, hi, 200)
    grid = pd.DataFrame({col: np.full_like(age, X_poly[col].mean()) for col in X_poly.columns})
    grid["Age"], grid["Age_sq"] = age, age ** 2
    grid = sm.add_constant((grid - X_poly.mean()) / X_poly.std(), has_constant="add")
    pred = model.get_prediction(grid).summary_frame(alpha=0.05)
    scale = y.std() / 1e6
    mean, low, high = (pred[c] * scale + y.mean() / 1e6 for c in ("mean", "mean_ci_lower", "mean_ci_upper"))

    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.fill_between(age, low, high, color="#86b6ef", alpha=0.5, linewidth=0)
    ax.plot(age, mean, color="#2a78d6", linewidth=2)
    ax.axvline(peak, color="#52514e", linewidth=1, linestyle=":")
    ax.annotate(f"peak at {peak:.0f} years", xy=(peak, mean.max()), xytext=(8, -70),
                textcoords="offset points", color="#0b0b0b", fontsize=10)
    ax.set_xlabel("Building age in 2022 (years)")
    ax.set_ylabel("Predicted site energy use (million kBtu)")
    ax.grid(True, color="#e5e4e0", linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()
    fig.savefig(ROOT / "figures" / "age_effect.png", dpi=200)
    plt.close(fig)


def residual_plot(model, title, filename):
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(model.fittedvalues, model.resid, s=6, alpha=0.3)
    ax.axhline(0, color="black", linewidth=1)
    ax.set_xlabel("Fitted values (standardized)")
    ax.set_ylabel("Residuals")
    ax.set_title(title)
    ax.grid(True, linestyle="--", alpha=0.5)
    fig.tight_layout()
    fig.savefig(ROOT / "figures" / filename, dpi=200)
    plt.close(fig)


def main():
    df = load_from_csv() if "--csv" in sys.argv else load_from_mysql()
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "figures").mkdir(exist_ok=True)
    print(f"records: {len(df):,}")

    y = df["total_energy_use"]
    X = pd.DataFrame({
        "GFA": df["total_gfa"],
        "Age": REFERENCE_YEAR - df["year_built"],
        "Electricity": df["electricity_use"],
    })

    describe(df, X)

    linear = ols(y, X)
    keep = X["GFA"] > 0
    log_linear = ols(y[keep], X[keep].assign(GFA=np.log(X.loc[keep, "GFA"])).rename(columns={"GFA": "log_GFA"}))
    X_poly = X.assign(GFA_sq=X["GFA"] ** 2, Age_sq=X["Age"] ** 2)
    polynomial = ols(y, X_poly)

    for name, model in (("Linear", linear), ("Log-linear", log_linear), ("Polynomial", polynomial)):
        print(f"\n===== {name} model =====\n{model.summary()}")

    comparison = pd.DataFrame(
        [(name, m.rsquared, m.rsquared_adj, m.aic, m.bic)
         for name, m in (("Linear", linear), ("Log-linear", log_linear), ("Polynomial", polynomial))],
        columns=["Model", "R²", "Adj R²", "AIC", "BIC"])
    comparison.to_csv(ROOT / "results" / "model_comparison.csv", index=False)
    print("\n===== Model comparison =====")
    print(comparison.round({"R²": 3, "Adj R²": 3, "AIC": 0, "BIC": 0}).to_string(index=False))

    coefficients = pd.DataFrame({"coef": polynomial.params, "std_err": polynomial.bse,
                                 "t": polynomial.tvalues, "p": polynomial.pvalues})
    coefficients.to_csv(ROOT / "results" / "polynomial_coefficients.csv")
    print("\n===== Polynomial model coefficients (standardized) =====")
    print(coefficients.round(4).to_string())

    rows = [("Linear", col, partial_r2(linear, ols(y, X.drop(columns=col)))) for col in X.columns]
    groups = {"GFA + GFA²": ["GFA", "GFA_sq"], "Age + Age²": ["Age", "Age_sq"], "Electricity": ["Electricity"]}
    rows += [("Polynomial", label, partial_r2(polynomial, ols(y, X_poly.drop(columns=cols))))
             for label, cols in groups.items()]
    partial = pd.DataFrame(rows, columns=["Model", "Predictor", "Partial R²"])
    partial.to_csv(ROOT / "results" / "partial_r2.csv", index=False)
    print("\n===== Partial R² (grouped for the polynomial model) =====")
    print(partial.round(4).to_string(index=False))

    peak = age_peak(polynomial, X_poly)
    print(f"\nPolynomial model peaks at a building age of {peak:.1f} years (built around {REFERENCE_YEAR - peak:.0f})")
    age_effect_plot(polynomial, X_poly, y, peak)

    residual_plot(linear, "Residuals vs fitted, linear model", "residuals_linear.png")
    residual_plot(polynomial, "Residuals vs fitted, polynomial model", "residuals_polynomial.png")


if __name__ == "__main__":
    main()
