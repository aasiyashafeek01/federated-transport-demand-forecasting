"""
GeoFed Transit Intelligence Platform
=====================================
insights_engine.py

Three insight layers:
1. Trend analysis    — YoY growth / decline / stable (existing)
2. Anomaly detection — sudden single-month shocks via Z-score (NEW)
3. Service pattern   — weekday vs weekend demand balance (NEW)

No ML jargon in outputs — everything is transport-authority language.

Author: GeoFed Transit Project
"""

import numpy as np
import pandas as pd
from datetime import datetime
from sklearn.preprocessing import StandardScaler
from data_manager import FEATURE_COLS, TARGET_COL
from client_manager import ClientManager


# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

RECENT_WINDOW      = 3      # months for "recent" trend window
GROWTH_THRESHOLD   = 0.10   # +10% YoY → growing
DECLINE_THRESHOLD  = -0.10  # -10% YoY → declining
SURGE_THRESHOLD    = 0.20   # +20% → critical high demand
CRITICAL_THRESHOLD = -0.20  # -20% → critical decline

# Anomaly detection
ANOMALY_ZSCORE     = 2.5    # Z-score threshold for anomaly flag
ANOMALY_WINDOW     = 24     # months of history for Z-score baseline

# Service pattern thresholds
WEEKDAY_DOMINANT   = 0.80   # >80% weekday share → commuter route
WEEKEND_BALANCED   = 0.55   # <55% weekday share → leisure/mixed route


# ─────────────────────────────────────────────
# InsightsEngine
# ─────────────────────────────────────────────

class InsightsEngine:
    """
    Translates federated model predictions into actionable
    transport planning insights across three layers:
      1. Trend analysis    (YoY growth / decline / stable)
      2. Anomaly detection (sudden demand shocks via Z-score)
      3. Service pattern   (weekday vs weekend demand balance)
    """

    def __init__(self, client_manager: ClientManager, trainer):
        self.cm = client_manager
        self.trainer = trainer

    # ─────────────────────────────────────────
    # Main Public API
    # ─────────────────────────────────────────

    def get_all_insights(self) -> dict:
        """Full insight report for all active clients. Called by the API."""
        client_insights = []
        all_route_flags = []

        for cid in self.cm.get_active_client_ids():
            try:
                insight = self._analyze_client(cid)
                client_insights.append(insight)
                all_route_flags.extend(insight.get("top_routes", []))
            except Exception as e:
                print(f"[InsightsEngine] Warning: client {cid} — {e}")

        return {
            "generated_at": datetime.now().isoformat(),
            "system_summary": self._system_summary(client_insights),
            "client_insights": client_insights,
            "top_priority_routes": self._get_priority_routes(all_route_flags),
            "network_health": self._network_health(client_insights),
            "network_anomalies": self._collect_network_anomalies(client_insights),
        }

    def get_client_insight(self, client_id: int) -> dict:
        """Single client insight — used by Operator Portal."""
        return self._analyze_client(client_id)

    def get_forecast_chart_data(self, client_id: int) -> dict:
        """Actual vs predicted monthly time series for charting."""
        try:
            data = self.cm.get_client_dataframe(client_id)
            data = data.dropna(subset=FEATURE_COLS + [TARGET_COL])
            data = data.copy()
            data["predicted"] = self._predict(data)

            temp = data[["Month_Beginning", TARGET_COL]].copy()
            temp["predicted"] = data["predicted"]
            monthly = (
                temp.groupby("Month_Beginning")
                .agg(actual=(TARGET_COL, "sum"), predicted=("predicted", "sum"))
                .reset_index()
                .sort_values("Month_Beginning")
                .tail(36)
            )
            return {
                "client_id": client_id,
                "chart_data": [
                    {
                        "month": row["Month_Beginning"].strftime("%Y-%m"),
                        "actual": round(float(row["actual"])),
                        "predicted": round(float(row["predicted"])),
                    }
                    for _, row in monthly.iterrows()
                ],
            }
        except Exception as e:
            return {"error": str(e)}

    # ─────────────────────────────────────────
    # Client Analysis (all three layers)
    # ─────────────────────────────────────────

    def _analyze_client(self, client_id: int) -> dict:
        """Full three-layer analysis for one client."""
        info = self.cm.get_client_info(client_id)
        data = self.cm.get_client_dataframe(client_id)
        data = data.dropna(subset=FEATURE_COLS + [TARGET_COL])

        if len(data) == 0:
            return {"client_id": client_id, "error": "No data available"}

        data = data.copy()
        data["predicted"] = self._predict(data)

        # Monthly aggregate
        monthly = (
            data.groupby("Month_Beginning")
            .agg(
                actual_demand=(TARGET_COL, "sum"),
                predicted_demand=("predicted", "sum"),
            )
            .reset_index()
            .sort_values("Month_Beginning")
        )

        # ── Layer 1: Trend ────────────────────────────────────────────
        baseline_avg, recent_avg = self._yoy_baseline(monthly)
        trend_pct = self._trend_pct(baseline_avg, recent_avg)
        trend_direction = self._trend_direction(trend_pct)
        recommendation = self._recommend(trend_pct)
        next_month_forecast = self._next_month_forecast(monthly)

        # ── Layer 2: Anomaly detection ────────────────────────────────
        anomalies = self._detect_anomalies(data, client_id)

        # ── Layer 3: Service pattern ──────────────────────────────────
        service_pattern = self._analyze_service_pattern(data)

        # ── Route-level trend flags ───────────────────────────────────
        route_analysis = self._analyze_routes(data, client_id)

        return {
            "client_id": client_id,
            "name": info["name"],
            "n_routes": info["n_routes"],
            "centroid_lat": info["centroid_lat"],
            "centroid_lon": info["centroid_lon"],

            # Layer 1 — Trend
            "baseline_monthly_demand": round(float(baseline_avg)),
            "recent_monthly_demand": round(float(recent_avg)),
            "next_month_forecast": round(float(next_month_forecast)),
            "trend_pct": round(float(trend_pct) * 100, 1),
            "trend_direction": trend_direction,
            "alert_level": recommendation["alert_level"],
            "status_label": recommendation["status_label"],
            "recommendation": recommendation["action"],
            "detail": recommendation["detail"],

            # Layer 2 — Anomalies
            "anomalies": anomalies,
            "has_anomalies": len(anomalies) > 0,

            # Layer 3 — Service pattern
            "service_pattern": service_pattern,

            # Routes
            "top_routes": route_analysis["flagged_routes"],
            "route_summary": route_analysis["summary"],
        }

    # ─────────────────────────────────────────
    # Layer 2: Anomaly Detection
    # ─────────────────────────────────────────

    def _detect_anomalies(self, data: pd.DataFrame, client_id: int) -> list:
        """
        Detect routes with sudden single-month demand shocks.

        Method: Z-score on each route's monthly history.
        Z > ANOMALY_ZSCORE (2.5) = statistically unusual vs own history.

        Catches sudden events (road closures, service changes, major events)
        that gradual trend analysis would miss entirely.
        """
        anomalies = []

        for route_id, route_df in data.groupby("route_id"):
            route_df = route_df.sort_values("Month_Beginning")
            history = route_df[TARGET_COL].values

            if len(history) < 12:
                continue

            # Baseline = last ANOMALY_WINDOW months excluding very last
            baseline_vals = (
                history[-ANOMALY_WINDOW:-1]
                if len(history) >= ANOMALY_WINDOW
                else history[:-1]
            )
            mean = float(np.mean(baseline_vals))
            std = float(np.std(baseline_vals))

            if std < 1:
                continue

            latest = float(history[-1])
            zscore = (latest - mean) / std

            if abs(zscore) >= ANOMALY_ZSCORE:
                direction = "spike" if zscore > 0 else "drop"
                pct_change = ((latest - mean) / mean * 100) if mean != 0 else 0

                anomalies.append({
                    "client_id": client_id,
                    "route_id": str(route_id),
                    "routename": route_df["routename"].iloc[0],
                    "anomaly_type": direction,
                    "zscore": round(float(zscore), 2),
                    "recent_demand": round(latest),
                    "historical_avg": round(mean),
                    "pct_change": round(float(pct_change), 1),
                    "alert_level": "critical" if abs(zscore) >= 3.5 else "warning",
                    "message": (
                        f"Unusual {'surge' if direction == 'spike' else 'drop'} on "
                        f"Route {route_id} ({route_df['routename'].iloc[0]}): "
                        f"{abs(pct_change):.0f}% "
                        f"{'above' if direction == 'spike' else 'below'} "
                        f"historical average. Investigate external factors."
                    ),
                })

        anomalies.sort(key=lambda x: -abs(x["zscore"]))
        return anomalies[:5]  # top 5 per client

    # ─────────────────────────────────────────
    # Layer 3: Service Pattern Analysis
    # ─────────────────────────────────────────

    def _analyze_service_pattern(self, data: pd.DataFrame) -> dict:
        """
        Classify routes by weekday vs weekend demand balance.

        Uses Avg_Weekday_Rides, Avg_Saturday_Rides, Avg_Sunday-Holiday_Rides.

        Three patterns:
          commuter_dominant  weekday share >80%  → peak-hour express focus
          leisure_mixed      weekday share <55%  → consistent all-week frequency
          balanced           55-80% weekday      → standard mixed service
        """
        # Use last 6 months per route for current pattern
        recent = data.sort_values("Month_Beginning")
        recent = recent.groupby("route_id").tail(6)

        route_patterns = []

        for route_id, rdf in recent.groupby("route_id"):
            wd = float(rdf["Avg_Weekday_Rides"].mean())
            sat = float(rdf["Avg_Saturday_Rides"].mean())
            sun = float(rdf["Avg_Sunday-Holiday_Rides"].mean())
            total = wd + sat + sun

            if total < 1:
                continue

            wd_share = wd / total

            if wd_share >= WEEKDAY_DOMINANT:
                pattern = "commuter_dominant"
                label = "Commuter Route"
                icon = "🚆"
                rec = (
                    "High weekday concentration. Consider express or limited-stop "
                    "service during peak hours (7–9am, 4–7pm). "
                    "Off-peak and weekend frequency can be reduced without major impact."
                )
            elif wd_share <= WEEKEND_BALANCED:
                pattern = "leisure_mixed"
                label = "Leisure / Mixed Route"
                icon = "🎭"
                rec = (
                    "Strong weekend demand relative to weekdays. "
                    "Maintain consistent frequency across all days. "
                    "Weekend service cuts would significantly impact this route."
                )
            else:
                pattern = "balanced"
                label = "Balanced Route"
                icon = "⚖️"
                rec = (
                    "Demand is well-distributed across the week. "
                    "Standard service schedule is appropriate."
                )

            route_patterns.append({
                "route_id": str(route_id),
                "routename": rdf["routename"].iloc[0],
                "pattern": pattern,
                "pattern_label": label,
                "pattern_icon": icon,
                "weekday_share_pct": round(wd_share * 100, 1),
                "avg_weekday_rides": round(wd),
                "avg_saturday_rides": round(sat),
                "avg_sunday_rides": round(sun),
                "recommendation": rec,
            })

        if not route_patterns:
            return {"routes": [], "summary": {}, "dominant_pattern": "unknown",
                    "client_schedule_recommendation": "Insufficient data."}

        counts = {}
        for r in route_patterns:
            counts[r["pattern"]] = counts.get(r["pattern"], 0) + 1

        dominant = max(counts, key=counts.get)

        if dominant == "commuter_dominant":
            client_rec = (
                "This region is primarily commuter-oriented. "
                "Prioritise peak-hour capacity and consider express overlays on busy corridors. "
                "Reducing off-peak frequency on low-ridership routes can improve cost efficiency."
            )
        elif dominant == "leisure_mixed":
            client_rec = (
                "This region has strong leisure and mixed-use demand. "
                "Consistent all-week frequency is essential — weekend service cuts "
                "would disproportionately affect this region's riders."
            )
        else:
            client_rec = (
                "Demand is balanced across the week in this region. "
                "Standard mixed-service scheduling is appropriate."
            )

        return {
            "routes": route_patterns,
            "summary": {
                "commuter_routes": counts.get("commuter_dominant", 0),
                "leisure_routes": counts.get("leisure_mixed", 0),
                "balanced_routes": counts.get("balanced", 0),
                "total_routes_analyzed": len(route_patterns),
            },
            "dominant_pattern": dominant,
            "client_schedule_recommendation": client_rec,
        }

    # ─────────────────────────────────────────
    # Route-Level Trend Flags
    # ─────────────────────────────────────────

    def _analyze_routes(self, data: pd.DataFrame, client_id: int) -> dict:
        """Trend-based flagging for individual routes within a client."""
        flagged = []

        for route_id, route_df in data.groupby("route_id"):
            route_df = route_df.sort_values("Month_Beginning")
            if len(route_df) < 6:
                continue

            route_monthly = (
                route_df.groupby("Month_Beginning")
                .agg(
                    actual_demand=(TARGET_COL, "sum"),
                    predicted_demand=("predicted", "sum"),
                )
                .reset_index()
                .sort_values("Month_Beginning")
            )

            baseline, recent = self._yoy_baseline(route_monthly)
            if baseline == 0:
                continue

            trend_pct = self._trend_pct(baseline, recent)
            rec = self._recommend(trend_pct)

            if rec["alert_level"] in ("critical", "warning"):
                flagged.append({
                    "client_id": client_id,
                    "route_id": str(route_id),
                    "routename": route_df["routename"].iloc[0],
                    "baseline_demand": round(baseline),
                    "recent_demand": round(recent),
                    "trend_pct": round(trend_pct * 100, 1),
                    "trend_direction": self._trend_direction(trend_pct),
                    "alert_level": rec["alert_level"],
                    "status_label": rec["status_label"],
                    "recommendation": rec["action"],
                })

        flagged.sort(key=lambda x: (
            0 if x["alert_level"] == "critical" else 1,
            -abs(x["trend_pct"]),
        ))

        return {
            "flagged_routes": flagged[:10],
            "summary": {
                "total_routes": data["route_id"].nunique(),
                "routes_needing_attention": len(flagged),
                "high_demand_count": sum(
                    1 for r in flagged if r["trend_direction"] == "growing"
                ),
                "declining_count": sum(
                    1 for r in flagged if r["trend_direction"] == "declining"
                ),
            },
        }

    # ─────────────────────────────────────────
    # Recommendation Logic
    # ─────────────────────────────────────────

    def _recommend(self, trend_pct: float) -> dict:
        pct_abs = abs(trend_pct) * 100

        if trend_pct >= SURGE_THRESHOLD:
            return {
                "alert_level": "critical",
                "status_label": "🔴 High Demand — Capacity Review Needed",
                "action": "Deploy additional buses. Increase service frequency during peak hours.",
                "detail": (
                    f"Demand is {pct_abs:.0f}% above last year's level. "
                    f"Current fleet is likely insufficient. Recommend immediate capacity review."
                ),
            }
        elif trend_pct >= GROWTH_THRESHOLD:
            return {
                "alert_level": "warning",
                "status_label": "🟡 Growing Demand — Monitor Closely",
                "action": "Consider increasing bus frequency on key routes.",
                "detail": (
                    f"Demand is {pct_abs:.0f}% above last year and trending upward. "
                    f"No immediate action required but monitor over next 2–3 months."
                ),
            }
        elif trend_pct <= CRITICAL_THRESHOLD:
            return {
                "alert_level": "critical",
                "status_label": "🔴 Critical Decline — Service Reassessment Required",
                "action": "Reduce frequency or reallocate buses to high-demand routes.",
                "detail": (
                    f"Demand is {pct_abs:.0f}% below last year's level. "
                    f"Recommend route consolidation or frequency reduction."
                ),
            }
        elif trend_pct <= DECLINE_THRESHOLD:
            return {
                "alert_level": "warning",
                "status_label": "🟡 Declining Demand — Efficiency Review",
                "action": "Review route efficiency. Consider reduced off-peak frequency.",
                "detail": (
                    f"Demand is {pct_abs:.0f}% below last year. "
                    f"Recommend reviewing off-peak schedules for cost efficiency."
                ),
            }
        else:
            return {
                "alert_level": "good",
                "status_label": "🟢 Stable — No Action Required",
                "action": "Maintain current fleet allocation and service frequency.",
                "detail": (
                    f"Demand is within {pct_abs:.0f}% of last year's level. "
                    f"Service levels are appropriate."
                ),
            }

    # ─────────────────────────────────────────
    # System Summaries
    # ─────────────────────────────────────────

    def _system_summary(self, client_insights: list) -> dict:
        valid = [c for c in client_insights if "error" not in c]
        if not valid:
            return {}

        growing   = [c for c in valid if c["trend_direction"] == "growing"]
        declining = [c for c in valid if c["trend_direction"] == "declining"]
        critical  = [c for c in valid if c["alert_level"] == "critical"]
        with_anomalies = [c for c in valid if c.get("has_anomalies")]

        return {
            "total_operators": len(valid),
            "total_next_month_forecast": round(sum(c["next_month_forecast"] for c in valid)),
            "operators_growing": len(growing),
            "operators_declining": len(declining),
            "operators_stable": len(valid) - len(growing) - len(declining),
            "operators_needing_attention": len(critical),
            "operators_with_anomalies": len(with_anomalies),
            "network_trend": (
                "growing"   if len(growing) > len(declining) else
                "declining" if len(declining) > len(growing) else
                "stable"
            ),
            "avg_trend_pct": round(float(np.mean([c["trend_pct"] for c in valid])), 1),
        }

    def _network_health(self, client_insights: list) -> dict:
        valid = [c for c in client_insights if "error" not in c]
        if not valid:
            return {"score": 0, "label": "Unknown", "color": "gray"}

        score_map = {"good": 100, "info": 75, "warning": 40, "critical": 10}
        base_score = float(np.mean([score_map.get(c["alert_level"], 50) for c in valid]))

        # Anomalies apply a small penalty to health score
        anomaly_penalty = sum(min(len(c.get("anomalies", [])) * 3, 10) for c in valid)
        score = round(max(0, base_score - anomaly_penalty))

        if score >= 80:
            label, color = "Healthy", "green"
        elif score >= 55:
            label, color = "Moderate", "yellow"
        else:
            label, color = "Needs Attention", "red"

        return {"score": score, "label": label, "color": color}

    def _get_priority_routes(self, all_flags: list) -> list:
        critical = sorted(
            [r for r in all_flags if r["alert_level"] == "critical"],
            key=lambda x: -abs(x["trend_pct"]),
        )
        warnings = sorted(
            [r for r in all_flags if r["alert_level"] == "warning"],
            key=lambda x: -abs(x["trend_pct"]),
        )
        return (critical + warnings)[:15]

    def _collect_network_anomalies(self, client_insights: list) -> list:
        """Flatten all client anomalies into one network-wide list."""
        all_anomalies = []
        for c in client_insights:
            if "error" not in c:
                all_anomalies.extend(c.get("anomalies", []))
        all_anomalies.sort(key=lambda x: -abs(x.get("zscore", 0)))
        return all_anomalies[:10]

    # ─────────────────────────────────────────
    # Prediction Helper
    # ─────────────────────────────────────────

    def _predict(self, data: pd.DataFrame) -> np.ndarray:
        """Centralised prediction with inverse-transform to original units."""
        gp = getattr(self.trainer, "global_params", {}) or {}
        X = data[FEATURE_COLS].values

        x_mean  = gp.get("x_mean",  None)
        x_scale = gp.get("x_scale", None)
        y_mean  = gp.get("y_mean",  0.0)
        y_scale = gp.get("y_scale", 1.0)
        coef    = gp.get("coef",    np.zeros(X.shape[1]))
        intercept = gp.get("intercept", 0.0)

        if x_mean is not None and x_scale is not None:
            X_s = (X - x_mean) / np.maximum(x_scale, 1e-8)
        else:
            X_s = StandardScaler().fit_transform(X)

        return (X_s @ coef + intercept) * y_scale + y_mean

    # ─────────────────────────────────────────
    # Stat Helpers
    # ─────────────────────────────────────────

    def _yoy_baseline(self, monthly: pd.DataFrame) -> tuple:
        monthly = monthly.sort_values("Month_Beginning").reset_index(drop=True)
        n = len(monthly)

        if n < 15:
            mid = max(1, n - RECENT_WINDOW)
            return (
                float(monthly["actual_demand"].iloc[:mid].mean()),
                float(monthly["predicted_demand"].iloc[-RECENT_WINDOW:].mean()),
            )

        recent = float(monthly["predicted_demand"].iloc[-RECENT_WINDOW:].mean())
        yoy_start = n - RECENT_WINDOW - 12
        yoy_end   = n - 12

        if yoy_start >= 0:
            baseline = float(monthly["actual_demand"].iloc[yoy_start:yoy_end].mean())
        else:
            baseline = float(monthly["actual_demand"].iloc[:-RECENT_WINDOW].tail(24).mean())

        return baseline, recent

    def _trend_pct(self, baseline: float, recent: float) -> float:
        return 0.0 if baseline == 0 else (recent - baseline) / baseline

    def _trend_direction(self, trend_pct: float) -> str:
        if trend_pct >= GROWTH_THRESHOLD:
            return "growing"
        if trend_pct <= DECLINE_THRESHOLD:
            return "declining"
        return "stable"

    def _next_month_forecast(self, monthly: pd.DataFrame) -> float:
        preds = monthly["predicted_demand"].values
        if len(preds) < 2:
            return float(preds[-1]) if len(preds) else 0.0
        window = preds[-6:] if len(preds) >= 6 else preds
        x = np.arange(len(window))
        slope, intercept = np.polyfit(x, window, 1)
        return float(max(0, intercept + slope * len(window)))


# ─────────────────────────────────────────────
# Quick test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    from data_manager import DataManager
    from federated_trainer import FederatedTrainer, FEDAVG

    dm = DataManager()
    dm.load_and_prepare()
    cm = ClientManager(dm)
    cm.initialize()

    print("Training global model...")
    trainer = FederatedTrainer(cm, algorithm=FEDAVG, n_rounds=5)
    trainer.train()

    engine = InsightsEngine(cm, trainer)
    report = engine.get_all_insights()

    print("\n── System Summary ──")
    s = report["system_summary"]
    print(f"  Total operators:          {s['total_operators']}")
    print(f"  Network trend:            {s['network_trend']}")
    print(f"  Avg trend:                {s['avg_trend_pct']}%")
    print(f"  Growing / Declining:      {s['operators_growing']} / {s['operators_declining']}")
    print(f"  Needing attention:        {s['operators_needing_attention']}")
    print(f"  Operators with anomalies: {s['operators_with_anomalies']}")
    print(f"  Next month forecast:      {s['total_next_month_forecast']:,}")

    print(f"\n── Network Health ──")
    h = report["network_health"]
    print(f"  Score: {h['score']}/100  |  {h['label']}")

    print("\n── Per-Client Insights ──")
    for c in report["client_insights"]:
        if "error" in c:
            continue
        print(f"\n  [{c['client_id']}] {c['name']}")
        print(f"    Trend:     {c['trend_pct']:+.1f}% ({c['trend_direction']})")
        print(f"    Status:    {c['status_label']}")
        print(f"    Forecast:  {c['next_month_forecast']:,} passengers next month")

        # Anomalies
        if c["anomalies"]:
            print(f"    Anomalies: {len(c['anomalies'])} detected")
            for a in c["anomalies"][:2]:
                print(f"      ⚡ Route {a['route_id']}: {a['anomaly_type']} "
                      f"Z={a['zscore']:+.1f} ({a['pct_change']:+.0f}%)")
        else:
            print(f"    Anomalies: none")

        # Service pattern
        sp = c["service_pattern"]["summary"]
        dom = c["service_pattern"]["dominant_pattern"]
        print(f"    Pattern:   {dom} "
              f"({sp.get('commuter_routes',0)} commuter / "
              f"{sp.get('leisure_routes',0)} leisure / "
              f"{sp.get('balanced_routes',0)} balanced)")

    print("\n── Top Priority Routes ──")
    for r in report["top_priority_routes"][:5]:
        print(f"  {r['alert_level'].upper():<8} | "
              f"Client {r['client_id']} | "
              f"Route {r['route_id']} ({r['routename']}) | "
              f"Trend: {r['trend_pct']:+.1f}%")

    print("\n── Network Anomalies ──")
    if report["network_anomalies"]:
        for a in report["network_anomalies"][:3]:
            print(f"  ⚡ {a['message']}")
    else:
        print("  No anomalies detected across network.")