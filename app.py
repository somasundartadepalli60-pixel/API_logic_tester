from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename
import sqlite3, json, os, re, time, uuid
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
import requests
import yaml

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "apipath_sentinel.db")
UPLOAD_DIR = os.path.join(APP_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = "local-development-key-change-before-sharing"
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
ALLOWED_SPEC_EXTS = {".json", ".yaml", ".yml"}
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS specs (
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
          filename TEXT NOT NULL, imported_at TEXT NOT NULL, raw_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS endpoints (
          id INTEGER PRIMARY KEY AUTOINCREMENT, spec_id INTEGER NOT NULL,
          path TEXT NOT NULL, method TEXT NOT NULL, summary TEXT DEFAULT '',
          operation_id TEXT DEFAULT '', parameters_json TEXT DEFAULT '[]',
          request_body_json TEXT DEFAULT '{}',
          FOREIGN KEY(spec_id) REFERENCES specs(id) ON DELETE CASCADE,
          UNIQUE(spec_id, path, method)
        );
        CREATE TABLE IF NOT EXISTS permissions (
          id INTEGER PRIMARY KEY AUTOINCREMENT, endpoint_id INTEGER NOT NULL,
          role TEXT NOT NULL, expected TEXT NOT NULL DEFAULT 'allow',
          notes TEXT DEFAULT '', updated_at TEXT NOT NULL,
          FOREIGN KEY(endpoint_id) REFERENCES endpoints(id) ON DELETE CASCADE,
          UNIQUE(endpoint_id, role)
        );
        CREATE TABLE IF NOT EXISTS runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT, endpoint_id INTEGER NOT NULL,
          role TEXT NOT NULL, expected TEXT NOT NULL, observed TEXT NOT NULL,
          status TEXT NOT NULL, http_status INTEGER, url TEXT NOT NULL,
          duration_ms INTEGER, response_excerpt TEXT, evidence_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          FOREIGN KEY(endpoint_id) REFERENCES endpoints(id) ON DELETE CASCADE
        );
        """)
init_db()

def now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

def load_spec(file_storage):
    filename = secure_filename(file_storage.filename or "openapi.json")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_SPEC_EXTS:
        raise ValueError("Upload a .json, .yaml, or .yml OpenAPI file.")
    content = file_storage.read()
    if len(content) > 5 * 1024 * 1024:
        raise ValueError("Specification is too large (5 MB maximum).")
    try:
        if ext == ".json":
            spec = json.loads(content.decode("utf-8"))
        else:
            spec = yaml.safe_load(content.decode("utf-8"))
    except Exception as e:
        raise ValueError("Could not parse the specification: " + str(e)[:180])
    if not isinstance(spec, dict) or not isinstance(spec.get("paths"), dict):
        raise ValueError("The file does not look like an OpenAPI document: a paths object is required.")
    return filename, spec

def extract_endpoints(spec):
    found = []
    for path, path_item in spec.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        shared_params = path_item.get("parameters", []) if isinstance(path_item.get("parameters", []), list) else []
        for method, op in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(op, dict):
                continue
            params = list(shared_params)
            if isinstance(op.get("parameters"), list):
                params += op["parameters"]
            body = op.get("requestBody", {})
            found.append({
                "path": str(path), "method": method.upper(),
                "summary": str(op.get("summary") or op.get("description") or ""),
                "operation_id": str(op.get("operationId") or ""),
                "parameters": params, "request_body": body if isinstance(body, dict) else {}
            })
    return found

@app.context_processor
def inject_globals():
    return {"app_name": "APIPath Sentinel"}

@app.route("/")
def index():
    with db() as c:
        specs = c.execute("SELECT * FROM specs ORDER BY id DESC").fetchall()
        endpoint_count = c.execute("SELECT COUNT(*) FROM endpoints").fetchone()[0]
        run_count = c.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        failed_count = c.execute("SELECT COUNT(*) FROM runs WHERE status='FAIL'").fetchone()[0]
        recent = c.execute("""SELECT r.*, e.path, e.method FROM runs r JOIN endpoints e ON e.id=r.endpoint_id
                              ORDER BY r.id DESC LIMIT 6""").fetchall()
    return render_template("index.html", specs=specs, endpoint_count=endpoint_count,
                           run_count=run_count, failed_count=failed_count, recent=recent)

@app.route("/specs/import", methods=["POST"])
def import_spec():
    upload = request.files.get("spec_file")
    if not upload or not upload.filename:
        flash("Choose an OpenAPI JSON or YAML file.", "error")
        return redirect(url_for("index"))
    try:
        filename, spec = load_spec(upload)
        endpoints = extract_endpoints(spec)
        if not endpoints:
            raise ValueError("No supported HTTP operations were found under paths.")
        name = str(spec.get("info", {}).get("title") or filename)
        with db() as c:
            cur = c.execute("INSERT INTO specs(name,filename,imported_at,raw_json) VALUES(?,?,?,?)",
                            (name, filename, now(), json.dumps(spec)))
            spec_id = cur.lastrowid
            for ep in endpoints:
                c.execute("""INSERT OR IGNORE INTO endpoints
                  (spec_id,path,method,summary,operation_id,parameters_json,request_body_json)
                  VALUES(?,?,?,?,?,?,?)""",
                  (spec_id, ep["path"], ep["method"], ep["summary"], ep["operation_id"],
                   json.dumps(ep["parameters"]), json.dumps(ep["request_body"])))
        flash(f"Imported {len(endpoints)} operations from {name}.", "success")
        return redirect(url_for("spec_detail", spec_id=spec_id))
    except Exception as e:
        flash(str(e), "error")
        return redirect(url_for("index"))


@app.route("/specs/discover", methods=["POST"])
def discover_spec():
    """Fetch a user-supplied OpenAPI document or probe common documentation paths."""
    target = (request.form.get("api_url") or "").strip()
    authorized = request.form.get("authorized_discovery") == "yes"
    if not authorized:
        flash("Confirm you own this API or have permission to retrieve its documentation.", "error")
        return redirect(url_for("index"))
    parsed = urlparse(target)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        flash("Enter a valid http:// or https:// API base URL or direct OpenAPI document URL.", "error")
        return redirect(url_for("index"))
    # Probe only standard documentation locations; do not crawl arbitrary site pages.
    candidates = [target]
    if not parsed.path.lower().endswith((".json", ".yaml", ".yml")):
        root = target.rstrip("/")
        candidates.extend([root + path for path in (
            "/openapi.json", "/swagger.json", "/api-docs", "/v3/api-docs",
            "/openapi.yaml", "/openapi.yml", "/swagger/v1/swagger.json",
            "/api/openapi.json", "/api/swagger.json", "/docs/openapi.json"
        )])
    errors = []
    for candidate in dict.fromkeys(candidates):
        try:
            response = requests.get(candidate, headers={"Accept": "application/json, application/yaml, text/yaml"},
                                    timeout=8, allow_redirects=False, stream=True)
            if response.status_code != 200:
                errors.append(f"{candidate} returned HTTP {response.status_code}")
                response.close()
                continue
            content = response.raw.read(5 * 1024 * 1024 + 1, decode_content=True)
            response.close()
            if len(content) > 5 * 1024 * 1024:
                errors.append(f"{candidate} exceeded the 5 MB limit")
                continue
            text_content = content.decode("utf-8-sig")
            try:
                spec = json.loads(text_content)
            except Exception:
                spec = yaml.safe_load(text_content)
            if not isinstance(spec, dict) or not isinstance(spec.get("paths"), dict):
                errors.append(f"{candidate} is reachable but is not an OpenAPI/Swagger document")
                continue
            endpoints = extract_endpoints(spec)
            if not endpoints:
                errors.append(f"{candidate} contains no supported HTTP operations")
                continue
            name = str(spec.get("info", {}).get("title") or parsed.netloc + " API")
            with db() as c:
                cur = c.execute("INSERT INTO specs(name,filename,imported_at,raw_json) VALUES(?,?,?,?)",
                                (name, candidate, now(), json.dumps(spec)))
                spec_id = cur.lastrowid
                for ep in endpoints:
                    c.execute("""INSERT OR IGNORE INTO endpoints
                      (spec_id,path,method,summary,operation_id,parameters_json,request_body_json)
                      VALUES(?,?,?,?,?,?,?)""",
                      (spec_id, ep["path"], ep["method"], ep["summary"], ep["operation_id"],
                       json.dumps(ep["parameters"]), json.dumps(ep["request_body"])))
            flash(f"Discovered and imported {len(endpoints)} operations from {candidate}.", "success")
            return redirect(url_for("spec_detail", spec_id=spec_id))
        except (requests.RequestException, UnicodeDecodeError, ValueError, yaml.YAMLError) as e:
            errors.append(f"{candidate}: {str(e)[:100]}")
    flash("Could not automatically find an OpenAPI document. A normal website URL does not expose its API schema automatically. "
          "Try the site's API docs URL or upload its OpenAPI JSON/YAML. Checked: " + "; ".join(errors[:4]), "error")
    return redirect(url_for("index"))

@app.route("/specs/import-github", methods=["POST"])
def import_github_starter():
    """Import a bundled, curated subset of the official GitHub REST API docs."""
    path = os.path.join(APP_DIR, "github_rest_api_starter.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            spec = json.load(f)
        endpoints = extract_endpoints(spec)
        name = str(spec.get("info", {}).get("title") or "GitHub REST API Starter")
        with db() as c:
            cur = c.execute("INSERT INTO specs(name,filename,imported_at,raw_json) VALUES(?,?,?,?)",
                            (name, "github_rest_api_starter.json", now(), json.dumps(spec)))
            spec_id = cur.lastrowid
            for ep in endpoints:
                c.execute("""INSERT OR IGNORE INTO endpoints
                  (spec_id,path,method,summary,operation_id,parameters_json,request_body_json)
                  VALUES(?,?,?,?,?,?,?)""",
                  (spec_id, ep["path"], ep["method"], ep["summary"], ep["operation_id"],
                   json.dumps(ep["parameters"]), json.dumps(ep["request_body"])))
        flash(f"Imported {len(endpoints)} read-only operations from the GitHub REST API starter.", "success")
        return redirect(url_for("spec_detail", spec_id=spec_id))
    except Exception as e:
        flash("Could not load the bundled GitHub API starter: " + str(e)[:180], "error")
        return redirect(url_for("index"))

@app.route("/spec/<int:spec_id>")
def spec_detail(spec_id):
    with db() as c:
        spec = c.execute("SELECT * FROM specs WHERE id=?", (spec_id,)).fetchone()
        if not spec:
            flash("Specification not found.", "error")
            return redirect(url_for("index"))
        endpoints = c.execute("""SELECT e.*,
          (SELECT COUNT(*) FROM permissions p WHERE p.endpoint_id=e.id) AS role_count,
          (SELECT COUNT(*) FROM runs r WHERE r.endpoint_id=e.id) AS run_count
          FROM endpoints e WHERE e.spec_id=? ORDER BY e.path,e.method""", (spec_id,)).fetchall()
    return render_template("spec_detail.html", spec=spec, endpoints=endpoints)

@app.route("/endpoint/<int:endpoint_id>")
def endpoint_detail(endpoint_id):
    with db() as c:
        ep = c.execute("""SELECT e.*,s.name AS spec_name,s.id AS spec_id FROM endpoints e
                          JOIN specs s ON s.id=e.spec_id WHERE e.id=?""", (endpoint_id,)).fetchone()
        if not ep:
            flash("Endpoint not found.", "error")
            return redirect(url_for("index"))
        perms = c.execute("SELECT * FROM permissions WHERE endpoint_id=? ORDER BY role", (endpoint_id,)).fetchall()
        runs = c.execute("SELECT * FROM runs WHERE endpoint_id=? ORDER BY id DESC LIMIT 20", (endpoint_id,)).fetchall()
    return render_template("endpoint_detail.html", ep=ep, perms=perms, runs=runs)

@app.route("/endpoint/<int:endpoint_id>/permissions", methods=["POST"])
def save_permission(endpoint_id):
    role = (request.form.get("role") or "").strip()
    expected = request.form.get("expected", "allow")
    notes = (request.form.get("notes") or "").strip()
    if not role or len(role) > 80:
        flash("Enter a role name (maximum 80 characters).", "error")
    elif expected not in {"allow", "deny"}:
        flash("Expected access must be Allow or Deny.", "error")
    else:
        with db() as c:
            exists = c.execute("SELECT id FROM endpoints WHERE id=?", (endpoint_id,)).fetchone()
            if not exists:
                flash("Endpoint not found.", "error")
                return redirect(url_for("index"))
            c.execute("""INSERT INTO permissions(endpoint_id,role,expected,notes,updated_at)
              VALUES(?,?,?,?,?) ON CONFLICT(endpoint_id,role) DO UPDATE SET
              expected=excluded.expected,notes=excluded.notes,updated_at=excluded.updated_at""",
              (endpoint_id, role, expected, notes, now()))
        flash(f"Saved expected access for role '{role}'.", "success")
    return redirect(url_for("endpoint_detail", endpoint_id=endpoint_id))

def parse_headers(raw):
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except Exception:
        raise ValueError("Headers must be valid JSON, for example: {\"Authorization\":\"Bearer YOUR_TEST_TOKEN\"}")
    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k,v in value.items()):
        raise ValueError("Headers must be a JSON object with string keys and string values.")
    # Prevent accidental hop-by-hop or host overrides.
    forbidden = {"host", "content-length", "connection", "transfer-encoding"}
    if any(k.lower() in forbidden for k in value):
        raise ValueError("Host and transport-level headers cannot be overridden.")
    return value

def substitute_path(path, values):
    def repl(match):
        key = match.group(1)
        return str(values.get(key, "1"))
    return re.sub(r"\{([^{}]+)\}", repl, path)

def classify(status_code, expected):
    # 2xx/3xx means access was granted; 401/403 means denied.
    if 200 <= status_code < 400:
        observed = "allow"
    elif status_code in (401, 403):
        observed = "deny"
    else:
        observed = "inconclusive"
    if observed == "inconclusive":
        return observed, "INCONCLUSIVE"
    return observed, ("PASS" if observed == expected else "FAIL")

@app.route("/endpoint/<int:endpoint_id>/run", methods=["POST"])
def run_test(endpoint_id):
    # This tool only sends a single request to the explicit target supplied by the user.
    role = (request.form.get("role") or "").strip()
    base_url = (request.form.get("base_url") or "").strip()
    headers_raw = request.form.get("headers_json") or "{}"
    path_values_raw = request.form.get("path_values") or "{}"
    body_raw = request.form.get("body_json") or ""
    query_raw = request.form.get("query_json") or "{}"
    acknowledged = request.form.get("authorized") == "yes"
    if not acknowledged:
        flash("Confirm that you own the target or have written permission to test it.", "error")
        return redirect(url_for("endpoint_detail", endpoint_id=endpoint_id))
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        flash("Enter a valid http:// or https:// base URL without embedded credentials.", "error")
        return redirect(url_for("endpoint_detail", endpoint_id=endpoint_id))
    # Restrict redirects to avoid forwarding test credentials to another host.
    try:
        headers = parse_headers(headers_raw)
        path_values = json.loads(path_values_raw)
        query = json.loads(query_raw)
        if not isinstance(path_values, dict) or not isinstance(query, dict):
            raise ValueError("Path values and query parameters must be JSON objects.")
        body = json.loads(body_raw) if body_raw.strip() else None
        if body is not None and not isinstance(body, (dict, list, str, int, float, bool)):
            raise ValueError("Request body must be valid JSON.")
    except Exception as e:
        flash(str(e), "error")
        return redirect(url_for("endpoint_detail", endpoint_id=endpoint_id))
    with db() as c:
        ep = c.execute("SELECT * FROM endpoints WHERE id=?", (endpoint_id,)).fetchone()
        perm = c.execute("SELECT * FROM permissions WHERE endpoint_id=? AND role=?", (endpoint_id, role)).fetchone()
    if not ep:
        flash("Endpoint not found.", "error")
        return redirect(url_for("index"))
    if not perm:
        flash("Save an expected Allow/Deny rule for this role before running a test.", "error")
        return redirect(url_for("endpoint_detail", endpoint_id=endpoint_id))
    path = substitute_path(ep["path"], path_values)
    url = base_url.rstrip("/") + "/" + path.lstrip("/")
    # Avoid sending requests to localhost/private addresses unless user explicitly opts in via local target.
    # Local/private targets are often required for staging tests; authorization checkbox is mandatory.
    start = time.monotonic()
    try:
        kwargs = {"headers": headers, "params": query, "timeout": 12, "allow_redirects": False}
        if body is not None:
            kwargs["json"] = body
        response = requests.request(ep["method"], url, **kwargs)
        duration = int((time.monotonic() - start) * 1000)
        observed, status = classify(response.status_code, perm["expected"])
        excerpt = response.text[:1500]
        evidence = {
            "request": {"method": ep["method"], "url": response.request.url,
                        "headers_sent": {k: ("[REDACTED]" if k.lower() in {"authorization","cookie","x-api-key"} else v)
                                         for k,v in response.request.headers.items()},
                        "body": body, "query": query},
            "response": {"status_code": response.status_code,
                         "headers": dict(list(response.headers.items())[:30]),
                         "body_excerpt": excerpt},
            "interpretation": {"expected": perm["expected"], "observed": observed, "result": status,
                               "note": "Only 2xx/3xx is treated as allow and 401/403 as deny. Other statuses require manual review."}
        }
        http_status = response.status_code
    except requests.RequestException as e:
        duration = int((time.monotonic() - start) * 1000)
        observed, status, http_status = "inconclusive", "INCONCLUSIVE", None
        excerpt = str(e)[:1000]
        evidence = {"request": {"method": ep["method"], "url": url},
                    "response": {"error": excerpt},
                    "interpretation": {"expected": perm["expected"], "observed": observed, "result": status}}
    with db() as c:
        c.execute("""INSERT INTO runs(endpoint_id,role,expected,observed,status,http_status,url,duration_ms,
          response_excerpt,evidence_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
          (endpoint_id, role, perm["expected"], observed, status, http_status, url, duration,
           excerpt, json.dumps(evidence), now()))
        run_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    flash(f"Test #{run_id}: {status} ({http_status if http_status is not None else 'no HTTP response'}).", "success" if status=="PASS" else ("error" if status=="FAIL" else "warning"))
    return redirect(url_for("run_detail", run_id=run_id))

@app.route("/run/<int:run_id>")
def run_detail(run_id):
    with db() as c:
        run = c.execute("""SELECT r.*,e.path,e.method,e.id AS endpoint_id,s.id AS spec_id
          FROM runs r JOIN endpoints e ON e.id=r.endpoint_id JOIN specs s ON s.id=e.spec_id
          WHERE r.id=?""", (run_id,)).fetchone()
    if not run:
        flash("Test evidence not found.", "error")
        return redirect(url_for("index"))
    evidence = json.loads(run["evidence_json"])
    return render_template("run_detail.html", run=run, evidence=evidence)

@app.route("/run/<int:run_id>/evidence.json")
def evidence_json(run_id):
    with db() as c:
        run = c.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    if not run:
        return jsonify({"error":"not found"}), 404
    return app.response_class(run["evidence_json"], mimetype="application/json",
                              headers={"Content-Disposition": f"attachment; filename=apipath-evidence-{run_id}.json"})

@app.route("/reports")
def reports():
    with db() as c:
        runs = c.execute("""SELECT r.*,e.path,e.method FROM runs r JOIN endpoints e ON e.id=r.endpoint_id
          ORDER BY r.id DESC""").fetchall()
        counts = {row["status"]: row["n"] for row in c.execute("SELECT status,COUNT(*) n FROM runs GROUP BY status")}
    return render_template("reports.html", runs=runs, counts=counts)

@app.route("/endpoint/<int:endpoint_id>/delete-permission/<int:permission_id>", methods=["POST"])
def delete_permission(endpoint_id, permission_id):
    with db() as c:
        c.execute("DELETE FROM permissions WHERE id=? AND endpoint_id=?", (permission_id, endpoint_id))
    flash("Permission rule deleted.", "success")
    return redirect(url_for("endpoint_detail", endpoint_id=endpoint_id))

@app.route("/spec/<int:spec_id>/delete", methods=["POST"])
def delete_spec(spec_id):
    with db() as c:
        c.execute("DELETE FROM specs WHERE id=?", (spec_id,))
    flash("Specification and related records deleted.", "success")
    return redirect(url_for("index"))

@app.route("/health")
def health():
    return jsonify({"status":"ok","app":"APIPath Sentinel","time":now()})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
