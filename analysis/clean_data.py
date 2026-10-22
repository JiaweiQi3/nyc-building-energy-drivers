"""Clean the NYC Local Law 84 benchmarking extract for the regression analysis.

Usage: python clean_data.py <raw_extract.csv|.xlsx> [output.csv]

The input is an LL84 extract with the columns of data/nyc_ll84_cleaned.csv.
Steps:
1. Treat text placeholders ("Not Available", "N/A", "--", ...) as missing and drop
   rows missing any modeling variable.
2. Keep Year Built in [1800, 2022].
3. Remove outliers in Total GFA, grid electricity and site energy with an
   iterative 3-sigma rule, one column at a time.
"""
import sys
from pathlib import Path

import pandas as pd

NA_TOKENS = ["Not Available", "NOT AVAILABLE", "not available",
             "NA", "N/A", "na", "n/a", "", " ", ".", "--"]

YEAR = "Year Built"
GFA = "Total GFA"
ELEC = "Electricity Use - Grid Purchase (kBtu)"
ENERGY = "Weather Normalized Site Energy Use (kBtu)"


def load(path):
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path, na_values=NA_TOKENS)
    return pd.read_csv(path, na_values=NA_TOKENS)


def sigma_filter(values, k=3.0):
    """Index of the values left after repeatedly dropping points beyond k standard deviations."""
    kept = values.dropna()
    while True:
        sd = kept.std()
        if sd == 0:
            return kept.index
        inside = kept[(kept - kept.mean()).abs() <= k * sd]
        if len(inside) == len(kept):
            return kept.index
        kept = inside


def clean(df):
    print(f"rows in extract: {len(df):,}")
    df = df.dropna(subset=[YEAR, ELEC, ENERGY, GFA])
    print(f"after dropping missing values: {len(df):,}")
    df = df[df[YEAR].between(1800, 2022)]
    print(f"after Year Built filter: {len(df):,}")
    for col in (ELEC, ENERGY, GFA):
        df = df.loc[sigma_filter(df[col])]
        print(f"after 3-sigma filter on {col}: {len(df):,}")
    return df


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / "data" / "nyc_ll84_cleaned.csv"
    clean(load(sys.argv[1])).to_csv(out, index=False)
    print(f"saved {out}")
