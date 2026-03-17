"""
GeoFed Transit Intelligence Platform
=====================================
api.py

Flask REST API — bridges the frontend and the backend ML pipeline.

Design decisions:
- Model trained ONCE at startup and kept in memory
- Re-training via POST /api/federated/train updates the in-memory model
- All responses are JSON
- CORS enabled for React frontend on port 3000

Endpoints:
  GET  /api/status
  GET  /api/clients
  GET  /api/clients/<id>
  GET  /api/clients/<id>/insights
  GET  /api/clients/<id>/predictions

  POST /api/federated/train           body: { "algorithm": "fedavg"|"fedprox", "n_rounds": int }
  GET  /api/federated/results
  GET  /api/federated/compare

  GET  /api/insights
  GET  /api/map/regions

  POST /api/clients/<id>/approve      body: { "current_round": int }
  POST /api/clients/<id>/deactivate

Author: GeoFed Transit Project
"""

import traceback
from flask import Flask, jsonify, request
from flask_cors import CORS

from data_manager import DataManager
from client_manager import ClientManager
from federated_trainer import FederatedTrainer, FEDAVG, FEDPROX
from insights_engine import InsightsEngine


# ─────────────────────────────────────────────
# App Setup
# ─────────────────────────────────────────────

app = Flask(__name__)
CORS(app)  # Allow React frontend on localhost:3000


# ─────────────────────────────────────────────
# System Initialisation (runs once at startup)
# ─────────────────────────────────────────────

print("[GeoFed API] Initialising system...")

dm = DataManager()
dm.load_and_prepare()

cm = ClientManager(dm)
cm.initialize()

# Train initial global model with FedAvg on startup
trainer = FederatedTrainer(cm, algorithm=FEDAVG, n_rounds=5)
trainer.train()

engine = InsightsEngine(cm, trainer)

print("[GeoFed API] System ready. Starting server...")


# ─────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────

def error(msg, code=400):
    return jsonify({"error": msg}), code

def success(data):
    return jsonify(data)


# ─────────────────────────────────────────────
# Status
# ─────────────────────────────────────────────

@app.route("/api/status", methods=["GET"])
def status():
    """Health check — confirms system is ready."""
    results = trainer.get_results()
    return success({
        "status": "ready",
        "model_trained": trainer.global_params is not None,
        "algorithm": trainer.algorithm,
        "n_rounds_trained": len(results.get("rounds", [])),
        "final_mae": results.get("final_mae"),
        "active_clients": len(cm.get_active_client_ids()),
        "pending_clients": len(cm.get_pending_client_ids()),
    })


# ─────────────────────────────────────────────
# Clients
# ─────────────────────────────────────────────

@app.route("/api/clients", methods=["GET"])
def get_clients():
    """All clients — active and pending — with summary info."""
    registry = cm.get_registry_summary()
    return success(registry)


@app.route("/api/clients/<int:client_id>", methods=["GET"])
def get_client(client_id):
    """Single client info and performance metrics."""
    info = cm.get_client_info(client_id)
    if not info:
        return error(f"Client {client_id} not found", 404)

    # Per-client performance from global model
    perf = trainer.evaluate_per_client()
    client_perf = perf.get(client_id, {})

    return success({**info, "performance": client_perf})


@app.route("/api/clients/<int:client_id>/insights", methods=["GET"])
def get_client_insights(client_id):
    """
    Full insight report for one client.
    Used by the Operator Portal.
    """
    info = cm.get_client_info(client_id)
    if not info:
        return error(f"Client {client_id} not found", 404)

    if trainer.global_params is None:
        return error("Model not trained yet. Call POST /api/federated/train first.")

    try:
        insight = engine.get_client_insight(client_id)
        return success(insight)
    except Exception as e:
        traceback.print_exc()
        return error(str(e), 500)


@app.route("/api/clients/<int:client_id>/predictions", methods=["GET"])
def get_client_predictions(client_id):
    """
    Actual vs predicted monthly time series for one client.
    Used for the demand forecast chart in the Operator Portal.
    """
    info = cm.get_client_info(client_id)
    if not info:
        return error(f"Client {client_id} not found", 404)

    if trainer.global_params is None:
        return error("Model not trained yet.")

    try:
        predictions = trainer.get_client_predictions(client_id)
        chart_data = engine.get_forecast_chart_data(client_id)
        return success({
            **predictions,
            "chart_data": chart_data.get("chart_data", []),
        })
    except Exception as e:
        traceback.print_exc()
        return error(str(e), 500)


# ─────────────────────────────────────────────
# Federated Training
# ─────────────────────────────────────────────

@app.route("/api/federated/train", methods=["POST"])
def run_training():
    """
    Run federated learning training.

    Body (JSON):
      {
        "algorithm": "fedavg" | "fedprox",   (default: "fedavg")
        "n_rounds":  int                      (default: 5)
      }

    Resets and retrains the global model. Updates the insights engine.
    Returns convergence data for the dashboard chart.
    """
    global trainer, engine

    body = request.get_json(silent=True) or {}
    algorithm = body.get("algorithm", FEDAVG).lower()
    n_rounds = int(body.get("n_rounds", 5))
    client_ids = body.get("client_ids", None)  # Optional selective participation

    if algorithm not in (FEDAVG, FEDPROX):
        return error(f"Unknown algorithm '{algorithm}'. Use 'fedavg' or 'fedprox'.")

    if not (1 <= n_rounds <= 20):
        return error("n_rounds must be between 1 and 20.")

    # Validate client_ids if provided
    active_ids = cm.get_active_client_ids()
    if client_ids is not None:
        client_ids = [int(i) for i in client_ids if int(i) in active_ids]
        if len(client_ids) == 0:
            return error("No valid active client IDs provided.")

    try:
        # Reset trainer with new settings, keep same client manager
        trainer = FederatedTrainer(cm, algorithm=algorithm, n_rounds=n_rounds)
        trainer.train(force_clients=client_ids)

        # Update insights engine to use new trainer
        engine = InsightsEngine(cm, trainer)

        results = trainer.get_results()
        return success({
            "status": "training_complete",
            "algorithm": algorithm,
            "n_rounds": n_rounds,
            "final_mae": results.get("final_mae"),
            "final_rmse": results.get("final_rmse"),
            "convergence": results.get("rounds", []),
            "per_client_performance": trainer.evaluate_per_client(),
        })
    except Exception as e:
        traceback.print_exc()
        return error(str(e), 500)


@app.route("/api/federated/results", methods=["GET"])
def get_results():
    """
    Latest training results including convergence curve.
    Used by the Global FL Hub convergence chart.
    """
    if trainer.global_params is None:
        return error("Model not trained yet.")

    results = trainer.get_results()
    return success({
        **results,
        "per_client_performance": trainer.evaluate_per_client(),
    })


@app.route("/api/federated/compare", methods=["GET"])
def compare_algorithms():
    """
    Run both FedAvg and FedProx and return side-by-side convergence.
    Used for the algorithm comparison chart on the dashboard.

    Note: this runs two full training passes — takes ~5-10 seconds.
    """
    try:
        n_rounds = int(request.args.get("n_rounds", 5))
        if not (1 <= n_rounds <= 10):
            return error("n_rounds must be 1–10 for comparison.")

        # Run FedAvg
        t_avg = FederatedTrainer(cm, algorithm=FEDAVG, n_rounds=n_rounds)
        t_avg.train()
        avg_results = t_avg.get_results()

        # Run FedProx
        t_prox = FederatedTrainer(cm, algorithm=FEDPROX, n_rounds=n_rounds)
        t_prox.train()
        prox_results = t_prox.get_results()

        # Build side-by-side convergence table
        avg_rounds  = avg_results.get("rounds", [])
        prox_rounds = prox_results.get("rounds", [])
        n = min(len(avg_rounds), len(prox_rounds))

        comparison = [
            {
                "round": i + 1,
                "fedavg_mae":  avg_rounds[i]["global_mae"],
                "fedprox_mae": prox_rounds[i]["global_mae"],
                "fedavg_rmse":  avg_rounds[i]["global_rmse"],
                "fedprox_rmse": prox_rounds[i]["global_rmse"],
            }
            for i in range(n)
        ]

        return success({
            "n_rounds": n_rounds,
            "fedavg_final_mae":  avg_results.get("final_mae"),
            "fedprox_final_mae": prox_results.get("final_mae"),
            "fedavg_final_rmse":  avg_results.get("final_rmse"),
            "fedprox_final_rmse": prox_results.get("final_rmse"),
            "convergence_comparison": comparison,
        })
    except Exception as e:
        traceback.print_exc()
        return error(str(e), 500)


# ─────────────────────────────────────────────
# Insights
# ─────────────────────────────────────────────

@app.route("/api/insights", methods=["GET"])
def get_insights():
    """
    Full network insight report.
    Used by the Authority Insights dashboard.
    Includes trend analysis, anomaly detection, service patterns.
    """
    if trainer.global_params is None:
        return error("Model not trained yet.")

    try:
        report = engine.get_all_insights()
        return success(report)
    except Exception as e:
        traceback.print_exc()
        return error(str(e), 500)


# ─────────────────────────────────────────────
# Map
# ─────────────────────────────────────────────

@app.route("/api/map/regions", methods=["GET"])
def get_map_regions():
    """
    Client region data for the Chicago Leaflet map.
    Returns centroid coordinates + bounding boxes for each client.
    """
    try:
        regions = dm.get_map_regions()
        # Enrich with live trend data if model is trained
        if trainer.global_params is not None:
            perf = trainer.evaluate_per_client()
            for region in regions:
                cid = region.get("client_id")
                region["performance"] = perf.get(cid, {})
        return success({"regions": regions})
    except Exception as e:
        traceback.print_exc()
        return error(str(e), 500)


# ─────────────────────────────────────────────
# Dynamic Client Management
# ─────────────────────────────────────────────

@app.route("/api/clients/<int:client_id>/approve", methods=["POST"])
def approve_client(client_id):
    """
    Approve a pending client (onboard them into FL training).

    Body (JSON):
      { "current_round": int }   (optional, defaults to 0)
    """
    body = request.get_json(silent=True) or {}
    current_round = int(body.get("current_round", 0))

    try:
        result = cm.approve_client(client_id, current_round)
        if not result:
            return error(f"Client {client_id} not found or not pending.", 404)

        info = cm.get_client_info(client_id)
        return success({
            "status": "approved",
            "client_id": client_id,
            "name": info["name"],
            "message": (
                f"{info['name']} has been approved and will participate "
                f"from round {current_round} onward."
            ),
        })
    except Exception as e:
        traceback.print_exc()
        return error(str(e), 500)


@app.route("/api/clients/<int:client_id>/deactivate", methods=["POST"])
def deactivate_client(client_id):
    """Deactivate an active client (remove from FL training)."""
    try:
        result = cm.deactivate_client(client_id)
        if not result:
            return error(f"Client {client_id} not found or not active.", 404)

        return success({
            "status": "deactivated",
            "client_id": client_id,
            "message": f"Client {client_id} has been deactivated.",
        })
    except Exception as e:
        traceback.print_exc()
        return error(str(e), 500)


# ─────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000)