"""
GeoFed Transit Intelligence Platform
=====================================
federated_trainer.py

Responsible for:
- Local model training at each client (LinearRegression)
- Proper weighted FedAvg aggregation
- FedProx aggregation (proximal regularization)
- Round-by-round training loop
- Storing per-round results and model states

Author: GeoFed Transit Project
"""

import numpy as np
import json
import pickle
from pathlib import Path
from datetime import datetime
from sklearn.linear_model import Ridge, SGDRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error
from sklearn.model_selection import train_test_split

from data_manager import DataManager, FEATURE_COLS, TARGET_COL
from client_manager import ClientManager


# ─────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent
RESULTS_PATH = BASE_DIR / "data" / "processed" / "fl_results.json"
MODELS_DIR = BASE_DIR / "data" / "processed" / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────
# Algorithm Constants
# ─────────────────────────────────────────────

FEDAVG = "fedavg"
FEDPROX = "fedprox"

# Number of local SGD passes per round
# More epochs = more local drift but faster convergence
LOCAL_EPOCHS = 5


# ─────────────────────────────────────────────
# Model Parameter Helpers
# ─────────────────────────────────────────────

def get_params(model) -> dict:
    """Extract coef_ and intercept_ from a fitted Ridge model."""
    return {
        "coef": model.coef_.copy(),
        "intercept": float(model.intercept_),
    }


def set_params(model, params: dict):
    """Set coef_ and intercept_ on a Ridge model (no retraining)."""
    model.coef_ = params["coef"].copy()
    model.intercept_ = params["intercept"]
    return model


def zero_params(n_features: int) -> dict:
    """Create zeroed parameter dict."""
    return {
        "coef": np.zeros(n_features),
        "intercept": 0.0,
    }


def scale_params(params: dict, scalar: float) -> dict:
    """Multiply parameters by a scalar."""
    return {
        "coef": params["coef"] * scalar,
        "intercept": params["intercept"] * scalar,
    }


def add_params(p1: dict, p2: dict) -> dict:
    """Element-wise addition of two parameter dicts."""
    return {
        "coef": p1["coef"] + p2["coef"],
        "intercept": p1["intercept"] + p2["intercept"],
    }


# ─────────────────────────────────────────────
# FederatedTrainer Class
# ─────────────────────────────────────────────

class FederatedTrainer:
    """
    Runs federated learning rounds using FedAvg or FedProx.

    FedAvg:
        Global model = weighted average of local models
        Weight = client sample count / total samples

    FedProx:
        Same as FedAvg but each client's local objective includes
        a proximal term that penalizes deviation from the global model:
        L_local(w) + (mu/2) * ||w - w_global||^2
        This reduces client drift on non-IID data.
    """

    def __init__(
        self,
        client_manager: ClientManager,
        algorithm: str = FEDAVG,
        n_rounds: int = 10,
        participation_rate: float = 1.0,
        fedprox_mu: float = 0.01,
        alpha: float = 1.0,        # Ridge regularization
        test_size: float = 0.2,
        random_state: int = 42,
    ):
        self.cm = client_manager
        self.algorithm = algorithm.lower()
        self.n_rounds = n_rounds
        self.participation_rate = participation_rate
        self.fedprox_mu = fedprox_mu
        self.alpha = alpha
        self.test_size = test_size
        self.random_state = random_state

        # Global model state
        self.global_params = None
        self.global_model = None
        self.n_features = len(FEATURE_COLS)

        # Training history
        self.rounds_history = []
        self.is_trained = False

        # Per-client local models (latest)
        self.local_models: dict[int, dict] = {}

    # ─────────────────────────────────────────
    # Main Training Loop
    # ─────────────────────────────────────────

    def train(self, n_rounds: int = None, force_clients: list = None) -> dict:
        """
        Run the full federated training loop.
        force_clients: if provided, only these client IDs participate in every round.
        Returns the complete results dict.
        """
        rounds = n_rounds or self.n_rounds
        print(f"\n[FederatedTrainer] Starting {self.algorithm.upper()} "
              f"— {rounds} rounds, "
              f"participation={self.participation_rate:.0%}")

        # Only initialize to zeros if no prior training exists
        # Preserves state across calls for dynamic onboarding demo
        if self.global_params is None:
            self.global_params = zero_params(self.n_features)

        self._force_clients = force_clients  # Store for _run_round to use

        for round_num in range(1, rounds + 1):
            round_result = self._run_round(round_num)
            self.rounds_history.append(round_result)

            print(f"  Round {round_num:>2} | "
                  f"clients={len(round_result['participating_clients'])} | "
                  f"global_mae={round_result['global_mae']:>10.0f} | "
                  f"global_rmse={round_result['global_rmse']:>10.0f}")

        # Build and save final global model
        self.global_model = self._build_sklearn_model(self.global_params)
        self._save_results()
        self._save_global_model()
        self.is_trained = True

        print(f"\n[FederatedTrainer] Training complete.")
        print(f"  Final global MAE:  {self.rounds_history[-1]['global_mae']:,.0f}")
        print(f"  Final global RMSE: {self.rounds_history[-1]['global_rmse']:,.0f}")

        return self._build_results_dict()

    def run_one_round(self) -> dict:
        """
        Run a single additional round on top of current state.
        Used by the API for step-by-step round execution from the UI.
        """
        if self.global_params is None:
            self.global_params = zero_params(self.n_features)

        round_num = len(self.rounds_history) + 1
        round_result = self._run_round(round_num)
        self.rounds_history.append(round_result)

        # Rebuild global sklearn model
        self.global_model = self._build_sklearn_model(self.global_params)
        self._save_results()
        self._save_global_model()
        self.is_trained = True

        return round_result

    def reset(self):
        """Reset all training state — start fresh."""
        self.global_params = None
        self.global_model = None
        self.rounds_history = []
        self.local_models = {}
        self.is_trained = False
        print("[FederatedTrainer] Reset complete.")

    # ─────────────────────────────────────────
    # Core Round Logic
    # ─────────────────────────────────────────

    def _run_round(self, round_num: int) -> dict:
        """Execute one complete FL round."""

        # 1. Sample participating clients
        # If force_clients set, use exactly those — otherwise use normal sampling
        if hasattr(self, '_force_clients') and self._force_clients is not None:
            participating = [c for c in self._force_clients if c in self.cm.get_active_client_ids()]
        else:
            participating = self.cm.sample_clients(self.participation_rate)

        # 2. Each client trains locally
        local_updates = {}
        client_metrics = {}
        sample_counts = {}

        for cid in participating:
            update, metrics, n = self._local_train(cid)
            if update is not None:
                local_updates[cid] = update
                client_metrics[cid] = metrics
                sample_counts[cid] = n
                self.cm.record_participation(cid, round_num)
                self.local_models[cid] = {
                    "params": update,
                    "metrics": metrics,
                    "round": round_num,
                }

        # 3. Aggregate updates → new global params
        if local_updates:
            self.global_params = self._aggregate(local_updates, sample_counts)

        # 4. Evaluate global model on all active clients
        global_mae, global_rmse = self._evaluate_global()

        # 5. Build round result
        return {
            "round": round_num,
            "algorithm": self.algorithm,
            "participating_clients": participating,
            "n_participating": len(participating),
            "client_metrics": {
                str(k): v for k, v in client_metrics.items()
            },
            "global_mae": global_mae,
            "global_rmse": global_rmse,
            "timestamp": datetime.now().isoformat(),
        }

    def _local_train(self, client_id: int):
        """
        Train a local model for one client using SGDRegressor.

        Both X and y are scaled during training for SGD stability.
        Evaluation is done in original (unscaled) units for interpretability.

        WHY SGD: Ridge solves analytically — warm starting gives identical
        results every round (flat convergence). SGD takes iterative gradient
        steps so each round genuinely improves from the previous.
        """
        try:
            X, y = self.cm.get_client_xy(client_id)
            if len(X) < 10:
                return None, None, 0

            X_train, X_test, y_train, y_test = train_test_split(
                X, y,
                test_size=self.test_size,
                random_state=self.random_state,
            )

            # Scale features AND target for SGD stability
            x_scaler = StandardScaler()
            y_scaler = StandardScaler()

            X_train_s = x_scaler.fit_transform(X_train)
            X_test_s = x_scaler.transform(X_test)
            y_train_s = y_scaler.fit_transform(y_train.reshape(-1, 1)).ravel()

            # Build SGD model
            local_model = SGDRegressor(
                max_iter=1,
                learning_rate="constant",
                eta0=0.01,
                random_state=self.random_state,
                warm_start=True,
                penalty="l2",
                alpha=self.alpha * 0.001,
            )

            # Warm start: initialize from global params if available
            if self.global_params is not None and np.any(self.global_params["coef"] != 0):
                local_model.partial_fit(X_train_s[:1], y_train_s[:1])
                local_model.coef_ = self.global_params["coef"].copy()
                local_model.intercept_ = np.array([self.global_params["intercept"]])
            else:
                local_model.partial_fit(X_train_s, y_train_s)

            # LOCAL_EPOCHS gradient steps on local scaled data
            for _ in range(LOCAL_EPOCHS):
                local_model.partial_fit(X_train_s, y_train_s)

            # FedProx: proximal correction — pull toward global params
            if self.algorithm == FEDPROX and self.global_params is not None:
                mu = self.fedprox_mu
                local_model.coef_ = (
                    (1 - mu) * local_model.coef_
                    + mu * self.global_params["coef"]
                )
                local_model.intercept_ = np.array([
                    (1 - mu) * local_model.intercept_[0]
                    + mu * self.global_params["intercept"]
                ])

            # Evaluate: predict in scaled space, inverse transform for MAE/RMSE
            preds_s = local_model.predict(X_test_s)
            preds = y_scaler.inverse_transform(preds_s.reshape(-1, 1)).ravel()
            mae = float(mean_absolute_error(y_test, preds))
            rmse = float(np.sqrt(mean_squared_error(y_test, preds)))

            metrics = {
                "mae": round(mae, 2),
                "rmse": round(rmse, 2),
                "n_train": len(X_train),
                "n_test": len(X_test),
            }

            # Store y_scaler params so global evaluation can inverse transform
            # We store mean/scale so the global model can reconstruct predictions
            params = {
                "coef": local_model.coef_.copy(),
                "intercept": float(local_model.intercept_[0]),
                "y_mean": float(y_scaler.mean_[0]),
                "y_scale": float(y_scaler.scale_[0]),
                "x_mean": x_scaler.mean_.copy(),
                "x_scale": x_scaler.scale_.copy(),
            }

            return params, metrics, len(X_train)

        except Exception as e:
            print(f"  [Warning] Client {client_id} training failed: {e}")
            return None, None, 0

    # ─────────────────────────────────────────
    # Aggregation
    # ─────────────────────────────────────────

    def _aggregate(
        self,
        local_updates: dict,
        sample_counts: dict,
    ) -> dict:
        """
        Weighted FedAvg aggregation.
        Weight = client sample count / total samples.
        Only coef and intercept are aggregated — scaler params
        are stored separately per client for inverse transform.
        """
        total_samples = sum(sample_counts.values())
        if total_samples == 0:
            return self.global_params

        agg_coef = np.zeros(self.n_features)
        agg_intercept = 0.0

        # Store scaler info from all clients (weighted avg for global prediction)
        agg_y_mean = 0.0
        agg_y_scale = 0.0
        agg_x_mean = np.zeros(self.n_features)
        agg_x_scale = np.zeros(self.n_features)

        for cid, params in local_updates.items():
            weight = sample_counts[cid] / total_samples
            agg_coef += weight * params["coef"]
            agg_intercept += weight * params["intercept"]
            agg_y_mean += weight * params.get("y_mean", 0.0)
            agg_y_scale += weight * params.get("y_scale", 1.0)
            agg_x_mean += weight * params.get("x_mean", np.zeros(self.n_features))
            agg_x_scale += weight * params.get("x_scale", np.ones(self.n_features))

        return {
            "coef": agg_coef,
            "intercept": agg_intercept,
            "y_mean": agg_y_mean,
            "y_scale": max(agg_y_scale, 1e-8),  # prevent div by zero
            "x_mean": agg_x_mean,
            "x_scale": np.maximum(agg_x_scale, 1e-8),
        }

    # ─────────────────────────────────────────
    # Evaluation
    # ─────────────────────────────────────────

    def _evaluate_global(self):
        """
        Evaluate global model across all active clients.
        Uses aggregated scaler params to inverse transform predictions
        back to original passenger count units.
        """
        if self.global_params is None:
            return 0.0, 0.0

        all_y_true = []
        all_y_pred = []

        y_mean = self.global_params.get("y_mean", 0.0)
        y_scale = self.global_params.get("y_scale", 1.0)
        x_mean = self.global_params.get("x_mean", None)
        x_scale = self.global_params.get("x_scale", None)

        for cid in self.cm.get_active_client_ids():
            try:
                X, y = self.cm.get_client_xy(cid)
                if len(X) == 0:
                    continue

                # Apply global aggregated scaler
                if x_mean is not None and x_scale is not None:
                    X_s = (X - x_mean) / x_scale
                else:
                    X_s = X

                # Predict in scaled space
                preds_s = X_s @ self.global_params["coef"] + self.global_params["intercept"]

                # Inverse transform to original units
                preds = preds_s * y_scale + y_mean

                all_y_true.extend(y.tolist())
                all_y_pred.extend(preds.tolist())
            except Exception:
                continue

        if not all_y_true:
            return 0.0, 0.0

        mae = float(mean_absolute_error(all_y_true, all_y_pred))
        rmse = float(np.sqrt(mean_squared_error(all_y_true, all_y_pred)))
        return round(mae, 2), round(rmse, 2)

    def evaluate_per_client(self) -> dict:
        """
        Returns MAE and RMSE per client in original passenger count units.
        """
        if self.global_params is None:
            return {}

        y_mean = self.global_params.get("y_mean", 0.0)
        y_scale = self.global_params.get("y_scale", 1.0)
        x_mean = self.global_params.get("x_mean", None)
        x_scale = self.global_params.get("x_scale", None)

        results = {}
        for cid in self.cm.get_active_client_ids():
            try:
                X, y = self.cm.get_client_xy(cid)
                if len(X) == 0:
                    continue
                if x_mean is not None and x_scale is not None:
                    X_s = (X - x_mean) / x_scale
                else:
                    X_s = X
                preds_s = X_s @ self.global_params["coef"] + self.global_params["intercept"]
                preds = preds_s * y_scale + y_mean
                mae = float(mean_absolute_error(y, preds))
                rmse = float(np.sqrt(mean_squared_error(y, preds)))
                results[cid] = {
                    "mae": round(mae, 2),
                    "rmse": round(rmse, 2),
                    "n_samples": len(y),
                }
            except Exception as e:
                results[cid] = {"error": str(e)}

        return results

    def get_client_predictions(self, client_id: int) -> dict:
        """
        Generate demand predictions in original passenger count units.
        Returns time-series data for charting.
        """
        if self.global_params is None:
            return {"error": "Model not trained yet"}

        try:
            data = self.cm.get_client_dataframe(client_id)
            data = data.dropna(subset=FEATURE_COLS + [TARGET_COL])

            X = data[FEATURE_COLS].values
            y_true = data[TARGET_COL].values

            y_mean = self.global_params.get("y_mean", 0.0)
            y_scale = self.global_params.get("y_scale", 1.0)
            x_mean = self.global_params.get("x_mean", None)
            x_scale = self.global_params.get("x_scale", None)

            if x_mean is not None and x_scale is not None:
                X_s = (X - x_mean) / x_scale
            else:
                X_s = X

            preds_s = X_s @ self.global_params["coef"] + self.global_params["intercept"]
            y_pred = preds_s * y_scale + y_mean

            temp = data[["Month_Beginning", TARGET_COL]].copy()
            temp["predicted"] = y_pred
            monthly = (
                temp.groupby("Month_Beginning")
                .agg(actual=(TARGET_COL, "sum"), predicted=("predicted", "sum"))
                .reset_index()
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
                "mae": round(float(mean_absolute_error(y_true, y_pred)), 2),
                "rmse": round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 2),
            }

        except Exception as e:
            return {"error": str(e)}

    # ─────────────────────────────────────────
    # Model Construction
    # ─────────────────────────────────────────

    def _build_sklearn_model(self, params: dict):
        """
        Build a sklearn SGDRegressor from parameter dict.
        Used for global model evaluation and predictions.
        Note: SGD params are in scaled space — evaluation uses
        raw features scaled per-client, so this model is used
        only for parameter storage and transfer. Actual predictions
        go through get_client_predictions() which handles scaling.
        """
        model = SGDRegressor(
            max_iter=1,
            learning_rate="constant",
            eta0=0.001,
            warm_start=True,
            penalty="l2",
            alpha=self.alpha * 0.01,
        )
        model.coef_ = params["coef"].copy()
        model.intercept_ = np.array([params["intercept"]])
        model.n_features_in_ = self.n_features
        model.t_ = 1.0  # needed for sklearn internal state
        return model

    # ─────────────────────────────────────────
    # Persistence
    # ─────────────────────────────────────────

    def _save_results(self):
        """Save training history to fl_results.json."""
        results = self._build_results_dict()
        RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(RESULTS_PATH, "w") as f:
            json.dump(results, f, indent=2, default=str)

    def _save_global_model(self):
        """Save global model parameters to disk."""
        model_path = MODELS_DIR / f"global_model_{self.algorithm}.pkl"
        with open(model_path, "wb") as f:
            pickle.dump({
                "params": self.global_params,
                "algorithm": self.algorithm,
                "n_features": self.n_features,
                "feature_cols": FEATURE_COLS,
                "saved_at": datetime.now().isoformat(),
            }, f)

    def load_results(self) -> dict:
        """Load previously saved results from disk."""
        if RESULTS_PATH.exists():
            with open(RESULTS_PATH, "r") as f:
                return json.load(f)
        return {}

    def get_results(self) -> dict:
        """Public method — returns current training results. Called by the API."""
        return self._build_results_dict()

    def _build_results_dict(self) -> dict:
        """Build clean results dict for API responses."""
        final_mae  = self.rounds_history[-1]["global_mae"]  if self.rounds_history else None
        final_rmse = self.rounds_history[-1]["global_rmse"] if self.rounds_history else None
        return {
            "status": "completed" if self.is_trained else "in_progress",
            "algorithm": self.algorithm,
            "total_rounds": len(self.rounds_history),
            "n_features": self.n_features,
            "feature_cols": FEATURE_COLS,
            "final_mae": final_mae,
            "final_rmse": final_rmse,
            "rounds": self.rounds_history,
            "convergence": {
                "mae_history":  [r["global_mae"]  for r in self.rounds_history],
                "rmse_history": [r["global_rmse"] for r in self.rounds_history],
            },
        }


# ─────────────────────────────────────────────
# Quick test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    # Setup
    dm = DataManager()
    dm.load_and_prepare()
    cm = ClientManager(dm)
    cm.initialize()

    print("\n" + "="*60)
    print("  TEST 1: FedAvg — 5 rounds")
    print("="*60)
    trainer_avg = FederatedTrainer(
        cm, algorithm=FEDAVG, n_rounds=5, participation_rate=1.0
    )
    results_avg = trainer_avg.train()

    print("\n── Per-client performance (FedAvg) ──")
    for cid, metrics in trainer_avg.evaluate_per_client().items():
        print(f"  Client {cid}: MAE={metrics['mae']:>10,.0f}  "
              f"RMSE={metrics['rmse']:>10,.0f}")

    print("\n" + "="*60)
    print("  TEST 2: FedProx — 5 rounds")
    print("="*60)
    trainer_prox = FederatedTrainer(
        cm, algorithm=FEDPROX, n_rounds=5,
        participation_rate=1.0, fedprox_mu=0.01
    )
    results_prox = trainer_prox.train()

    print("\n── Per-client performance (FedProx) ──")
    for cid, metrics in trainer_prox.evaluate_per_client().items():
        print(f"  Client {cid}: MAE={metrics['mae']:>10,.0f}  "
              f"RMSE={metrics['rmse']:>10,.0f}")

    print("\n" + "="*60)
    print("  TEST 3: Dynamic onboarding mid-training")
    print("="*60)
    cm2 = ClientManager(dm)
    cm2.initialize()
    trainer_dyn = FederatedTrainer(
        cm2, algorithm=FEDAVG, n_rounds=3
    )

    print("\n  Phase 1: 3 rounds with 8 clients")
    trainer_dyn.train(n_rounds=3)

    print("\n  Approving client 8 (North Shore Transit Co.)...")
    cm2.approve_client(8, current_round=3)

    print("\n  Phase 2: 2 more rounds with 9 clients")
    trainer_dyn.n_rounds = 2
    trainer_dyn.train(n_rounds=2)

    print("\n  Deactivating client 8...")
    cm2.deactivate_client(8)

    print("\n  Phase 3: 2 more rounds with 8 clients again")
    trainer_dyn.train(n_rounds=2)

    print("\n── FedAvg vs FedProx Convergence ──")
    print(f"  {'Round':<8} {'FedAvg MAE':>12} {'FedProx MAE':>12}")
    avg_mae = results_avg["convergence"]["mae_history"]
    prox_mae = results_prox["convergence"]["mae_history"]
    for i, (a, p) in enumerate(zip(avg_mae, prox_mae), 1):
        print(f"  {i:<8} {a:>12,.0f} {p:>12,.0f}")

    print("\n── Sample predictions (client 0) ──")
    pred = trainer_avg.get_client_predictions(0)
    if "chart_data" in pred:
        print(f"  MAE: {pred['mae']:,.0f}")
        print(f"  Sample months:")
        for row in pred["chart_data"][-3:]:
            print(f"    {row['month']}: actual={row['actual']:>8,}  "
                  f"predicted={row['predicted']:>8,}")