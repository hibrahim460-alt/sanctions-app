"""
Flask web app: dashboard + JSON API.

Endpoints:
  GET  /                  -> dashboard (frontend/index.html)
  POST /api/ingest        -> run a fetch/ingest cycle now
  GET  /api/stats         -> per-source last-updated + entry counts
  GET  /api/changes       -> recent change feed (added/removed/modified)
  GET  /api/screen?q=NAME -> screen a name against the current lists
"""

import os
from flask import Flask, jsonify, request, send_from_directory

import ingest
import storage

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

app = Flask(__name__)

# Native CORS configuration (Tells browsers it is safe to connect)
@app.after_request
def add_cors_headers(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    return response

# Initialize database collections and search indexes
storage.init_db()


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/api/ingest", methods=["POST"])
def api_ingest():
    return jsonify(ingest.run_ingest())


@app.route("/api/stats")
def api_stats():
    return jsonify({"sources": storage.stats()})


@app.route("/api/changes")
def api_changes():
    limit = int(request.args.get("limit", 200))
    return jsonify({"changes": storage.recent_changes(limit)})


@app.route("/api/screen")
def api_screen():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "missing q"}), 400
    threshold = float(request.args.get("threshold", 0.5))
    return jsonify({"query": q, "hits": ingest.screen_name(q, threshold)})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
