from flask import Flask, send_from_directory, Response, request, make_response
import os, glob, requests, sys

ROOT = os.path.dirname(os.path.abspath(__file__))

# ---- Find your entry HTML automatically ----
CANDIDATE_DIRS = [ROOT, os.path.join(ROOT, "public"), os.path.join(ROOT, "dist"), os.path.join(ROOT, "build")]

def find_entry():
    for d in CANDIDATE_DIRS:
        for name in ("index.html", "canva.html"):
            p = os.path.join(d, name)
            if os.path.exists(p):
                return d, name
    for d in CANDIDATE_DIRS:
        files = glob.glob(os.path.join(d, "*.html"))
        if files:
            return d, os.path.basename(files[0])
    return None, None

STATIC_DIR, ENTRY_FILE = find_entry()
print("App root:", ROOT)
if STATIC_DIR and ENTRY_FILE:
    print(f"✅ Serving {ENTRY_FILE} from: {STATIC_DIR}")
else:
    print("❌ No HTML found; / will 404 until you add one.")

app = Flask(__name__, static_folder=STATIC_DIR or ROOT, static_url_path="")

# ---- Proxy config ----
BASE = "https://cai.gss.com.tw"
TIMEOUT = 20  # seconds

def corsify(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp

# ---- WEBCHAT proxy (static loader assets etc.) ----
@app.route("/webchat/<path:path>", methods=["GET", "OPTIONS"])
def webchat_proxy(path):
    if request.method == "OPTIONS":
        return corsify(make_response("", 204))
    params = request.args.to_dict(flat=True)
    upstream = f"{BASE}/webchat/{path}"
    print(f"→ proxy GET {upstream} params={params}", file=sys.stderr)
    try:
        r = requests.get(upstream, params=params, timeout=TIMEOUT)
        resp = make_response(r.content, r.status_code)
        ct = r.headers.get("Content-Type")
        if ct: resp.headers["Content-Type"] = ct
        return corsify(resp)
    except requests.exceptions.RequestException as e:
        print(f"✗ proxy error {upstream}: {e}", file=sys.stderr)
        return corsify(make_response(f"Proxy error contacting {upstream}\n{e}", 502))

# ---- DIRECT LINE proxy (tokens/generate, conversations, activities, etc.) ----
@app.route("/directline/<path:path>", methods=["GET", "POST", "OPTIONS"])
def directline_proxy(path):
    if request.method == "OPTIONS":
        return corsify(make_response("", 204))

    upstream = f"{BASE}/productionLocalDirectLine/directline/{path}"
    params = request.args.to_dict(flat=True)

    # Pass through only needed headers
    fwd_headers = {}
    if "Content-Type" in request.headers:
        fwd_headers["Content-Type"] = request.headers["Content-Type"]
    if "Authorization" in request.headers:
        fwd_headers["Authorization"] = request.headers["Authorization"]

    data = request.get_data()
    print(f"→ DL {request.method} {upstream} params={params}", file=sys.stderr)

    try:
        r = requests.request(
            method=request.method,
            url=upstream,
            params=params,
            data=data,
            headers=fwd_headers,
            timeout=TIMEOUT,
        )
        resp = make_response(r.content, r.status_code)
        ct = r.headers.get("Content-Type")
        if ct: resp.headers["Content-Type"] = ct
        return corsify(resp)
    except requests.exceptions.RequestException as e:
        print(f"✗ DL proxy error {upstream}: {e}", file=sys.stderr)
        return corsify(make_response(f"Proxy error: {e}", 502))

# ---- Static serving ----
@app.route("/")
def root():
    if not ENTRY_FILE:
        return "No HTML file found.", 404
    return send_from_directory(STATIC_DIR, ENTRY_FILE)

@app.route("/<path:path>")
def assets(path):
    full = os.path.join(STATIC_DIR or ROOT, path)
    if os.path.exists(full):
        return send_from_directory(STATIC_DIR or ROOT, path)
    return "Not found", 404

if __name__ == "__main__":
    app.run(port=8000, debug=True)
