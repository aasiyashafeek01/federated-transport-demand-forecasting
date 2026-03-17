"""
GeoFed Transit Intelligence Platform
=====================================
client_manager.py

Responsible for:
- Managing all 8 active federated clients (geographic operators)
- Managing 2 reserve/pending clients for dynamic onboarding demo
- Handling client registration, activation, deactivation
- Providing per-client data splits to the trainer
- Tracking client metadata and participation history

Author: GeoFed Transit Project
"""

import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
from data_manager import DataManager, FEATURE_COLS, TARGET_COL


# ─────────────────────────────────────────────
# Client Status Constants
# ─────────────────────────────────────────────

STATUS_ACTIVE = "active"
STATUS_PENDING = "pending"       # waiting for admin approval
STATUS_INACTIVE = "inactive"     # deactivated / removed
STATUS_TRAINING = "training"     # currently training local model
STATUS_READY = "ready"           # trained, update ready to send


# ─────────────────────────────────────────────
# Reserve Client Config
# Two synthetic clients built from real data
# for the dynamic onboarding demo
# ─────────────────────────────────────────────

RESERVE_CLIENT_CONFIG = {
    8: {
        "name": "North Shore Transit Co.",
        "source_client_id": 6,   # borrow geographic region from client 6
        "fraction": 0.4,         # use 40% of that client's routes
        "noise_factor": 0.05,    # slight noise to differentiate
        "description": "Newly incorporated northern operator",
    },
    9: {
        "name": "Lakefront Express Authority",
        "source_client_id": 1,
        "fraction": 0.35,
        "noise_factor": 0.08,
        "description": "Lakefront corridor specialist operator",
    },
}

# Human-readable names for the 8 real clients
CLIENT_NAMES = {
    0: "South Side Transit",
    1: "West Loop Authority",
    2: "Far South Depot",
    3: "Southwest Transit",
    4: "Central Loop Operator",
    5: "North Chicago Transit",
    6: "Northwest Corridor",
    7: "Mid-South Authority",
}


# ─────────────────────────────────────────────
# ClientManager Class
# ─────────────────────────────────────────────

class ClientManager:
    """
    Manages all federated clients — active, pending, and inactive.

    Core responsibilities:
    - Split processed data by client_id
    - Build and serve per-client feature matrices
    - Handle dynamic client onboarding and deactivation
    - Track client metadata (name, status, data size, participation)
    """

    def __init__(self, data_manager: DataManager = None):
        self.dm = data_manager or DataManager()
        self.df = None

        # client_id → DataFrame
        self.clients: dict[int, pd.DataFrame] = {}

        # client_id → metadata dict
        self.client_registry: dict[int, dict] = {}

        self._initialized = False

    # ─────────────────────────────────────────
    # Initialization
    # ─────────────────────────────────────────

    def initialize(self):
        """
        Load data, partition into clients, build registry.
        Must be called once before anything else.
        """
        self.df = self.dm.get_data()
        self._partition_clients()
        self._build_registry()
        self._create_reserve_clients()
        self._initialized = True

        active = len(self.get_active_clients())
        pending = len(self.get_pending_clients())
        print(f"[ClientManager] Initialized: {active} active, {pending} pending clients")

    def _partition_clients(self):
        """Split main dataframe by client_id."""
        for cid in sorted(self.df["client_id"].unique()):
            self.clients[int(cid)] = self.df[
                self.df["client_id"] == cid
            ].copy().reset_index(drop=True)

    def _build_registry(self):
        """Build metadata registry for each real client."""
        for cid, data in self.clients.items():
            self.client_registry[cid] = {
                "client_id": cid,
                "name": CLIENT_NAMES.get(cid, f"Operator {cid}"),
                "status": STATUS_ACTIVE,
                "n_samples": len(data),
                "n_routes": data["route_id"].nunique(),
                "centroid_lat": float(data["centroid_lat"].mean()),
                "centroid_lon": float(data["centroid_lon"].mean()),
                "avg_monthly_demand": float(data[TARGET_COL].mean()),
                "demand_categories": data["demand_category"].value_counts().to_dict(),
                "joined_round": 0,
                "last_trained_round": None,
                "participation_count": 0,
                "created_at": datetime.now().isoformat(),
            }

    def _create_reserve_clients(self):
        """
        Build 2 synthetic pending clients from subsets of real client data.
        These are used for the dynamic onboarding demo.
        """
        for cid, config in RESERVE_CLIENT_CONFIG.items():
            source_df = self.clients[config["source_client_id"]].copy()

            # Take a fraction of routes
            routes = source_df["route_id"].unique()
            n_routes = max(1, int(len(routes) * config["fraction"]))
            selected_routes = np.random.choice(routes, n_routes, replace=False)
            subset = source_df[source_df["route_id"].isin(selected_routes)].copy()

            # Add slight noise to demand values to differentiate
            noise = np.random.normal(1.0, config["noise_factor"], len(subset))
            subset[TARGET_COL] = (subset[TARGET_COL] * noise).clip(lower=0)
            for col in FEATURE_COLS:
                if col in subset.columns:
                    noise_f = np.random.normal(1.0, config["noise_factor"] / 2, len(subset))
                    subset[col] = (subset[col] * noise_f).clip(lower=0)

            subset["client_id"] = cid
            self.clients[cid] = subset.reset_index(drop=True)

            self.client_registry[cid] = {
                "client_id": cid,
                "name": config["name"],
                "status": STATUS_PENDING,
                "n_samples": len(subset),
                "n_routes": subset["route_id"].nunique(),
                "centroid_lat": float(subset["centroid_lat"].mean()),
                "centroid_lon": float(subset["centroid_lon"].mean()),
                "avg_monthly_demand": float(subset[TARGET_COL].mean()),
                "demand_categories": subset["demand_category"].value_counts().to_dict(),
                "description": config["description"],
                "joined_round": None,
                "last_trained_round": None,
                "participation_count": 0,
                "created_at": datetime.now().isoformat(),
            }

    # ─────────────────────────────────────────
    # Data Access
    # ─────────────────────────────────────────

    def get_client_xy(self, client_id: int):
        """
        Returns (X, y) numpy arrays for a client.
        Used by federated_trainer for local training.
        """
        self._check_initialized()
        data = self.clients[client_id].copy()

        # Only use rows where all feature columns are present
        data = data.dropna(subset=FEATURE_COLS + [TARGET_COL])

        X = data[FEATURE_COLS].values.astype(np.float64)
        y = data[TARGET_COL].values.astype(np.float64)
        return X, y

    def get_client_dataframe(self, client_id: int) -> pd.DataFrame:
        """Returns full dataframe for a client."""
        self._check_initialized()
        return self.clients[client_id].copy()

    def get_client_sample_count(self, client_id: int) -> int:
        """Returns number of valid training samples for a client."""
        X, y = self.get_client_xy(client_id)
        return len(y)

    def get_all_sample_counts(self) -> dict:
        """Returns {client_id: n_samples} for all active clients."""
        return {
            cid: self.get_client_sample_count(cid)
            for cid in self.get_active_client_ids()
        }

    # ─────────────────────────────────────────
    # Client Queries
    # ─────────────────────────────────────────

    def get_active_clients(self) -> list[dict]:
        """Returns list of metadata dicts for all active clients."""
        return [
            v for v in self.client_registry.values()
            if v["status"] == STATUS_ACTIVE
        ]

    def get_pending_clients(self) -> list[dict]:
        """Returns list of metadata dicts for pending (not yet approved) clients."""
        return [
            v for v in self.client_registry.values()
            if v["status"] == STATUS_PENDING
        ]

    def get_inactive_clients(self) -> list[dict]:
        """Returns list of metadata dicts for inactive clients."""
        return [
            v for v in self.client_registry.values()
            if v["status"] == STATUS_INACTIVE
        ]

    def get_active_client_ids(self) -> list[int]:
        """Returns sorted list of active client IDs."""
        return sorted([c["client_id"] for c in self.get_active_clients()])

    def get_pending_client_ids(self) -> list[int]:
        """Returns sorted list of pending client IDs. Called by the API."""
        return sorted([c["client_id"] for c in self.get_pending_clients()])

    def get_all_clients(self) -> list[dict]:
        """Returns all clients regardless of status."""
        return list(self.client_registry.values())

    def get_client_info(self, client_id: int) -> dict:
        """Returns metadata for a specific client."""
        self._check_initialized()
        if client_id not in self.client_registry:
            raise ValueError(f"Client {client_id} not found in registry.")
        return self.client_registry[client_id].copy()

    # ─────────────────────────────────────────
    # Dynamic Participation
    # ─────────────────────────────────────────

    def approve_client(self, client_id: int, current_round: int = 0) -> dict:
        """
        Approve a pending client → makes them active.
        They will participate from the next FL round onward.
        """
        self._check_initialized()
        reg = self.client_registry.get(client_id)
        if reg is None:
            raise ValueError(f"Client {client_id} does not exist.")
        if reg["status"] != STATUS_PENDING:
            raise ValueError(f"Client {client_id} is not pending (status: {reg['status']}).")

        self.client_registry[client_id]["status"] = STATUS_ACTIVE
        self.client_registry[client_id]["joined_round"] = current_round
        print(f"[ClientManager] Client {client_id} ({reg['name']}) approved → active from round {current_round}")
        return self.client_registry[client_id]

    def deactivate_client(self, client_id: int) -> dict:
        """
        Deactivate an active client → removes them from future rounds.
        Their data and history are preserved.
        """
        self._check_initialized()
        reg = self.client_registry.get(client_id)
        if reg is None:
            raise ValueError(f"Client {client_id} does not exist.")
        if reg["status"] != STATUS_ACTIVE:
            raise ValueError(f"Client {client_id} is not active (status: {reg['status']}).")

        self.client_registry[client_id]["status"] = STATUS_INACTIVE
        print(f"[ClientManager] Client {client_id} ({reg['name']}) deactivated.")
        return self.client_registry[client_id]

    def reactivate_client(self, client_id: int) -> dict:
        """Reactivate a previously deactivated client."""
        self._check_initialized()
        self.client_registry[client_id]["status"] = STATUS_ACTIVE
        print(f"[ClientManager] Client {client_id} reactivated.")
        return self.client_registry[client_id]

    def record_participation(self, client_id: int, round_num: int):
        """Called by trainer to log that a client participated in a round."""
        if client_id in self.client_registry:
            self.client_registry[client_id]["last_trained_round"] = round_num
            self.client_registry[client_id]["participation_count"] += 1

    # ─────────────────────────────────────────
    # Sampling (for participation rate)
    # ─────────────────────────────────────────

    def sample_clients(self, participation_rate: float = 1.0) -> list[int]:
        """
        Randomly sample a fraction of active clients for a round.
        participation_rate=1.0 means all active clients participate.
        """
        active_ids = self.get_active_client_ids()
        if participation_rate >= 1.0:
            return active_ids
        n = max(1, int(len(active_ids) * participation_rate))
        return sorted(np.random.choice(active_ids, n, replace=False).tolist())

    # ─────────────────────────────────────────
    # Serialization (for API responses)
    # ─────────────────────────────────────────

    def get_registry_summary(self) -> dict:
        """Returns a clean summary of all clients for the dashboard."""
        return {
            "active": self.get_active_clients(),
            "pending": self.get_pending_clients(),
            "inactive": self.get_inactive_clients(),
            "counts": {
                "active": len(self.get_active_clients()),
                "pending": len(self.get_pending_clients()),
                "inactive": len(self.get_inactive_clients()),
            },
        }

    # ─────────────────────────────────────────
    # Internal
    # ─────────────────────────────────────────

    def _check_initialized(self):
        if not self._initialized:
            raise RuntimeError(
                "[ClientManager] Not initialized. Call initialize() first."
            )


# ─────────────────────────────────────────────
# Quick test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    dm = DataManager()
    dm.load_and_prepare()

    cm = ClientManager(dm)
    cm.initialize()

    print("\n── Registry Summary ──")
    summary = cm.get_registry_summary()
    print(f"  Active clients:  {summary['counts']['active']}")
    print(f"  Pending clients: {summary['counts']['pending']}")
    print(f"  Inactive clients:{summary['counts']['inactive']}")

    print("\n── Active Clients ──")
    for c in cm.get_active_clients():
        print(f"  [{c['client_id']}] {c['name']:<30} "
              f"routes={c['n_routes']:>3}  "
              f"samples={c['n_samples']:>5}  "
              f"avg_demand={c['avg_monthly_demand']:>10.0f}")

    print("\n── Pending Clients ──")
    for c in cm.get_pending_clients():
        print(f"  [{c['client_id']}] {c['name']:<30} "
              f"routes={c['n_routes']:>3}  "
              f"samples={c['n_samples']:>5}")

    print("\n── Sample client_xy shape (client 0) ──")
    X, y = cm.get_client_xy(0)
    print(f"  X: {X.shape}, y: {y.shape}")

    print("\n── Sample sizes (for FedAvg weighting) ──")
    counts = cm.get_all_sample_counts()
    total = sum(counts.values())
    for cid, n in sorted(counts.items()):
        print(f"  Client {cid}: {n} samples ({100*n/total:.1f}%)")

    print("\n── Dynamic onboarding demo ──")
    cm.approve_client(8, current_round=3)
    print(f"  Active after approval: {cm.get_active_client_ids()}")
    cm.deactivate_client(8)
    print(f"  Active after deactivation: {cm.get_active_client_ids()}")