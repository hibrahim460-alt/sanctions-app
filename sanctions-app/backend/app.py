"""
Flask web app: dashboard + JSON API.
"""

from flask import Flask, jsonify, request, send_from_directory
import os

# Straight direct imports matching your filesystem
import ingest
import storage
import suggest

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BACKEND_DIR, "..", "frontend")

app = Flask(__name__)

@app.after_request
def add_cors_headers(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    return response

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
    threshold = float(request.args.get("threshold", 0.80))
    return jsonify({"query": q, "hits": ingest.screen_name(q, threshold)})

@app.route("/api/variants")
def api_variants():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "missing q"}), 400
    from matching import generate_variants
    return jsonify({"query": q, "variants": generate_variants(q)})

@app.route("/api/suggest")
def api_suggest():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"query": "", "has_suggestions": False, "tokens": [], "did_you_mean": []})
    return jsonify(suggest.suggest(q))

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
