"""
GeoFed Transit Intelligence Platform
=====================================
data_manager.py

Responsible for:
- Loading final_merged_clients.csv
- Cleaning and validating data
- Feature engineering (lag features, temporal, demand categories)
- Providing clean data to the rest of the system

Author: GeoFed Transit Project
"""

import pandas as pd
import numpy as np
from pathlib import Path


# ─────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "data" / "processed" / "final_merged_clients.csv"


# ─────────────────────────────────────────────
# DataManager Class
# ─────────────────────────────────────────────

class DataManager:
    """
    Loads, cleans, and feature-engineers the CTA merged dataset.
    Acts as the single source of truth for data in the system.
    """

    def __init__(self, data_path: str = None):
        self.data_path = Path(data_path) if data_path else DATA_PATH
        self.df = None  # raw loaded dataframe
        self.processed_df = None  # cleaned + feature-engineered

    # ─────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────

    def load_and_prepare(self) -> pd.DataFrame:
        """
        Full pipeline: load → clean → engineer features.
        Returns the final processed DataFrame.
        """
        self._load()
        self._clean()
        self._engineer_features()
        print(f"[DataManager] Ready. Shape: {self.processed_df.shape}")
        return self.processed_df

    def get_data(self) -> pd.DataFrame:
        """Returns processed data. Auto-loads if not already loaded."""
        if self.processed_df is None:
            self.load_and_prepare()
        return self.processed_df

    def get_client_ids(self) -> list:
        """Returns sorted list of all client IDs (0–7)."""
        return sorted(self.get_data()["client_id"].unique().tolist())

    def get_client_data(self, client_id: int) -> pd.DataFrame:
        """Returns all data for a specific client."""
        df = self.get_data()
        return df[df["client_id"] == client_id].copy()

    def get_routes_for_client(self, client_id: int) -> list:
        """Returns list of route dicts for a client (for UI display)."""
        client_df = self.get_client_data(client_id)
        routes = (
            client_df.groupby("route_id")
            .agg(
                routename=("routename", "first"),
                avg_demand=("MonthTotal", "mean"),
                centroid_lat=("centroid_lat", "first"),
                centroid_lon=("centroid_lon", "first"),
                demand_category=("demand_category", "first"),
            )
            .reset_index()
        )
        return routes.to_dict(orient="records")

    def get_map_regions(self) -> list:
        """
        Returns region summary per client for the Chicago map.
        Each entry has centroid, client_id, route count, avg demand.
        """
        df = self.get_data()
        regions = (
            df.groupby("client_id")
            .agg(
                centroid_lat=("centroid_lat", "mean"),
                centroid_lon=("centroid_lon", "mean"),
                route_count=("route_id", "nunique"),
                avg_monthly_demand=("MonthTotal", "mean"),
                total_demand=("MonthTotal", "sum"),
            )
            .reset_index()
        )
        regions["client_id"] = regions["client_id"].astype(int)
        return regions.to_dict(orient="records")

    def get_summary_stats(self) -> dict:
        """Returns high-level stats for the dashboard."""
        df = self.get_data()
        return {
            "total_routes": int(df["route_id"].nunique()),
            "total_clients": int(df["client_id"].nunique()),
            "date_range": {
                "start": str(df["Month_Beginning"].min().date()),
                "end": str(df["Month_Beginning"].max().date()),
            },
            "total_records": int(len(df)),
            "avg_monthly_demand": float(df["MonthTotal"].mean()),
        }

    # ─────────────────────────────────────────
    # Internal Pipeline
    # ─────────────────────────────────────────

    def _load(self):
        """Load CSV from disk."""
        if not self.data_path.exists():
            raise FileNotFoundError(
                f"[DataManager] Dataset not found at: {self.data_path}\n"
                f"Make sure final_merged_clients.csv is in backend/data/processed/"
            )
        self.df = pd.read_csv(self.data_path)
        print(f"[DataManager] Loaded {len(self.df)} rows from {self.data_path.name}")

    def _clean(self):
        """Clean and validate the raw dataframe."""
        df = self.df.copy()

        # ── Parse dates ──────────────────────────────────────────────
        df["Month_Beginning"] = pd.to_datetime(df["Month_Beginning"], errors="coerce")
        df = df.dropna(subset=["Month_Beginning"])

        # ── Remove commas from numeric columns if present ─────────────
        numeric_cols = [
            "Avg_Weekday_Rides",
            "Avg_Saturday_Rides",
            "Avg_Sunday-Holiday_Rides",
            "MonthTotal",
        ]
        for col in numeric_cols:
            if df[col].dtype == object:
                df[col] = df[col].astype(str).str.replace(",", "").str.strip()
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # ── Fill zeros for Saturday/Sunday (some routes don't operate) ─
        # Zero is valid here — not missing, just no service
        df["Avg_Saturday_Rides"] = df["Avg_Saturday_Rides"].fillna(0.0)
        df["Avg_Sunday-Holiday_Rides"] = df["Avg_Sunday-Holiday_Rides"].fillna(0.0)

        # ── Drop rows where target variable is missing ────────────────
        df = df.dropna(subset=["MonthTotal", "Avg_Weekday_Rides"])

        # ── Ensure route_id is string (handles "8A", "J14" etc.) ──────
        df["route_id"] = df["route_id"].astype(str).str.strip()

        # ── Ensure client_id is integer ───────────────────────────────
        df["client_id"] = df["client_id"].astype(int)

        # ── Sort chronologically per route ───────────────────────────
        df = df.sort_values(["route_id", "Month_Beginning"]).reset_index(drop=True)

        # ── Remove extreme outliers (top 0.1% of MonthTotal) ──────────
        upper_bound = df["MonthTotal"].quantile(0.999)
        df = df[df["MonthTotal"] <= upper_bound]

        print(f"[DataManager] After cleaning: {len(df)} rows")
        self.df = df

    def _engineer_features(self):
        """Add temporal and demand features for forecasting."""
        df = self.df.copy()

        # ── Temporal features ────────────────────────────────────────
        df["year"] = df["Month_Beginning"].dt.year
        df["month_num"] = df["Month_Beginning"].dt.month

        # Cyclical month encoding (captures seasonality better than raw month)
        df["month_sin"] = np.sin(2 * np.pi * df["month_num"] / 12)
        df["month_cos"] = np.cos(2 * np.pi * df["month_num"] / 12)

        # Quarter
        df["quarter"] = df["Month_Beginning"].dt.quarter

        # ── Lag features (per route) ──────────────────────────────────
        df = df.sort_values(["route_id", "Month_Beginning"])

        df["demand_lag_1"] = df.groupby("route_id")["MonthTotal"].shift(1)
        df["demand_lag_3"] = df.groupby("route_id")["MonthTotal"].shift(3)
        df["demand_lag_12"] = df.groupby("route_id")["MonthTotal"].shift(12)

        # ── Rolling averages (per route) ──────────────────────────────
        df["demand_rolling_3"] = (
            df.groupby("route_id")["MonthTotal"]
            .transform(lambda x: x.shift(1).rolling(3, min_periods=1).mean())
        )
        df["demand_rolling_12"] = (
            df.groupby("route_id")["MonthTotal"]
            .transform(lambda x: x.shift(1).rolling(12, min_periods=1).mean())
        )

        # ── Month-over-month growth rate ──────────────────────────────
        df["demand_growth_rate"] = df.groupby("route_id")["MonthTotal"].pct_change()
        df["demand_growth_rate"] = df["demand_growth_rate"].replace(
            [np.inf, -np.inf], np.nan
        ).fillna(0.0)

        # ── Demand category (for non-IID analysis) ───────────────────
        # Based on each route's mean demand across all time
        route_avg = df.groupby("route_id")["MonthTotal"].transform("mean")
        p30 = route_avg.quantile(0.30)
        p70 = route_avg.quantile(0.70)

        df["demand_category"] = pd.cut(
            route_avg,
            bins=[-np.inf, p30, p70, np.inf],
            labels=["low", "medium", "high"],
        )

        # ── Fill NaN lag values with route mean (only for model input) ─
        lag_cols = ["demand_lag_1", "demand_lag_3", "demand_lag_12",
                    "demand_rolling_3", "demand_rolling_12"]
        for col in lag_cols:
            df[col] = df.groupby("route_id")[col].transform(
                lambda x: x.fillna(x.mean())
            )

        print(f"[DataManager] Feature engineering complete. Columns: {list(df.columns)}")
        self.processed_df = df


# ─────────────────────────────────────────────
# Feature column definitions
# (imported by other modules)
# ─────────────────────────────────────────────

FEATURE_COLS = [
    "Avg_Weekday_Rides",
    "Avg_Saturday_Rides",
    "Avg_Sunday-Holiday_Rides",
    "demand_lag_1",
    "demand_lag_3",
    "demand_rolling_3",
    "demand_rolling_12",
    "month_sin",
    "month_cos",
    "year",
]

TARGET_COL = "MonthTotal"


# ─────────────────────────────────────────────
# Quick test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    dm = DataManager()
    df = dm.load_and_prepare()

    print("\n── Summary Stats ──")
    for k, v in dm.get_summary_stats().items():
        print(f"  {k}: {v}")

    print("\n── Client IDs ──")
    print(dm.get_client_ids())

    print("\n── Map Regions (first 3) ──")
    for r in dm.get_map_regions()[:3]:
        print(f"  Client {r['client_id']}: "
              f"lat={r['centroid_lat']:.4f}, "
              f"lon={r['centroid_lon']:.4f}, "
              f"routes={r['route_count']}, "
              f"avg_demand={r['avg_monthly_demand']:.0f}")

    print("\n── Sample processed data ──")
    print(df[["route_id", "client_id", "MonthTotal",
              "demand_lag_1", "demand_rolling_3",
              "month_sin", "demand_category"]].head())