"""
DTC e-Bus Pass  –  Python API Backend
Requires: pip install pymongo dnspython requests
"""

import json
import os
import sys
import random
import base64
import io
import traceback
import string
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta, timezone
import socket

# ── Captcha store (in-memory, token → {text, expires}) ────────────────────────
_CAPTCHA_STORE = {}
CAPTCHA_TTL = 300  # seconds (5 minutes)

def _captcha_cleanup():
    now = time.time()
    expired = [k for k, v in _CAPTCHA_STORE.items() if v['expires'] < now]
    for k in expired:
        del _CAPTCHA_STORE[k]

def generate_captcha_token():
    """Create a random 6-char captcha, store it, return (token, text)."""
    _captcha_cleanup()
    text  = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    token = ''.join(random.choices(string.ascii_lowercase + string.digits, k=24))
    _CAPTCHA_STORE[token] = {'text': text, 'expires': time.time() + CAPTCHA_TTL}
    return token, text

def verify_captcha_token(token, user_input):
    """Return True if token exists and input matches (case-insensitive). Deletes token after use."""
    entry = _CAPTCHA_STORE.get(token)
    if not entry:
        return False
    if time.time() > entry['expires']:
        del _CAPTCHA_STORE[token]
        return False
    ok = entry['text'].upper() == user_input.strip().upper()
    del _CAPTCHA_STORE[token]  # one-time use
    return ok

def draw_captcha_image(text):
    """Draw captcha text as a simple PNG using only stdlib (no Pillow needed)."""
    # We'll generate an SVG and return it as image/svg+xml
    width, height = 180, 60
    chars = list(text)
    items = []
    colors = ['#c0392b','#2980b9','#27ae60','#8e44ad','#e67e22','#2c3e50']
    for i, ch in enumerate(chars):
        x = 15 + i * 27 + random.randint(-3, 3)
        y = 38 + random.randint(-5, 5)
        rot = random.randint(-18, 18)
        size = random.randint(22, 30)
        color = colors[i % len(colors)]
        items.append(
            f'<text x="{x}" y="{y}" transform="rotate({rot},{x},{y})" '
            f'font-size="{size}" font-family="monospace" font-weight="bold" '
            f'fill="{color}">{ch}</text>'
        )
    # Noise lines
    lines = []
    for _ in range(5):
        x1,y1 = random.randint(0,width), random.randint(0,height)
        x2,y2 = random.randint(0,width), random.randint(0,height)
        c = random.choice(['#bdc3c7','#95a5a6','#7f8c8d'])
        lines.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{c}" stroke-width="1.5"/>')
    # Noise dots
    dots = []
    for _ in range(30):
        cx,cy = random.randint(0,width), random.randint(0,height)
        dots.append(f'<circle cx="{cx}" cy="{cy}" r="1.5" fill="#bdc3c7"/>')
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'style="background:#f8f9fa;border-radius:6px;">'
        + ''.join(lines) + ''.join(dots) + ''.join(items)
        + '</svg>'
    )
    return svg.encode('utf-8')

print("[BOOT] api_server.py starting...", flush=True)
print(f"[BOOT] Python {sys.version}", flush=True)

try:
    import pymongo
    from pymongo import MongoClient
    HAS_MONGO = True
    print("[BOOT] pymongo imported OK", flush=True)
except ImportError as e:
    HAS_MONGO = False
    print(f"[BOOT] pymongo not available: {e}", flush=True)

try:
    import requests as req_lib
    HAS_REQUESTS = True
    print("[BOOT] requests imported OK", flush=True)
except ImportError as e:
    HAS_REQUESTS = False
    print(f"[BOOT] requests not available: {e}", flush=True)

# ── Load env vars ─────────────────────────────────────────────────────────────
# os.environ (Render dashboard) takes priority; .env file is local fallback only
def _load_env(path):
    cfg = {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, val = line.partition('=')
                cfg[key.strip()] = val.strip().strip('"').strip("'")
        print(f"[BOOT] Loaded .env from {path}", flush=True)
    except FileNotFoundError:
        print(f"[BOOT] No .env file found (OK on Render)", flush=True)
    return cfg

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
cfg = _load_env(ENV_PATH)

MONGODB_URI   = os.environ.get('MONGODB_URI')   or cfg.get('MONGODB_URI',   '')
IMGBB_API_KEY = os.environ.get('IMGBB_API_KEY') or cfg.get('IMGBB_API_KEY', '')
PORT          = int(os.environ.get('PORT')       or cfg.get('PORT', 5000))
HOST          = '0.0.0.0'

print(f"[BOOT] HOST={HOST} PORT={PORT}", flush=True)
print(f"[BOOT] MONGODB_URI={'SET (' + MONGODB_URI[:20] + '...)' if MONGODB_URI else 'NOT SET (will use mock DB)'}", flush=True)

# ── Global Settings (loaded from DB after connect) ────────────────────────────
ALLOW_REGISTRATION = True  # default; overwritten by DB value after connect

def _load_registration_setting():
    """Read allow_registration from MongoDB settings collection."""
    global ALLOW_REGISTRATION
    try:
        col = db_col._Collection__database['settings'] if hasattr(db_col, '_Collection__database') \
              else db_col._database['settings'] if hasattr(db_col, '_database') \
              else None
        if col is None:
            # Try direct client access if db_col is a real pymongo Collection
            col = db_col.database['settings']
        doc = col.find_one({'_id': 'registration'})
        if doc:
            ALLOW_REGISTRATION = bool(doc.get('allow_registration', True))
            print(f"[INFO] Loaded registration setting from DB: {ALLOW_REGISTRATION}", flush=True)
    except Exception as e:
        print(f"[WARN] Could not load registration setting from DB: {e}", flush=True)

def _save_registration_setting(value):
    """Persist allow_registration to MongoDB settings collection."""
    try:
        col = db_col.database['settings']
        col.update_one(
            {'_id': 'registration'},
            {'$set': {'allow_registration': value}},
            upsert=True
        )
        print(f"[INFO] Saved registration setting to DB: {value}", flush=True)
    except Exception as e:
        print(f"[WARN] Could not save registration setting to DB: {e}", flush=True)

# ── MongoDB connection ─────────────────────────────────────────────────────────
# ── Mock Database for Offline/Fallback Mode ────────────────────────────────────
try:
    from bson import ObjectId
except ImportError:
    class ObjectId:
        def __init__(self, val=None):
            self.val = val or os.urandom(12).hex()
        def __str__(self):
            return str(self.val)
        def __eq__(self, other):
            return str(self) == str(other)
        def __hash__(self):
            return hash(str(self))

class MockCollection:
    def __init__(self):
        self.passes = []
        # Seed with a default pass for testing/demo
        now = datetime.now(timezone.utc)
        self.passes.append({
            '_id': ObjectId('6443c5b96912b7a4cf8a27d2'),
            'passno': '7502032600973',
            'name': 'PAWAN KUMAR',
            'mobile': '9999999999',
            'dob': '01/01/2000',
            'photoUrl': 'images/pawan.jpg',
            'qrCodeUrl': '',
            'validFrom': now,
            'validTo': now + timedelta(days=150),
            'createdAt': now,
            'updatedAt': now,
        })

    def find(self, query=None):
        results = self.passes
        class Cursor:
            def __init__(self, data):
                self.data = data
            def sort(self, key, direction=1):
                # Simple sort by createdAt DESC
                if key == 'createdAt' and direction == -1:
                    return sorted(self.data, key=lambda x: x.get('createdAt', datetime.min), reverse=True)
                return self.data
            def __iter__(self):
                return iter(self.data)
        return Cursor(results)

    def find_one(self, query):
        for p in self.passes:
            match = True
            for k, v in query.items():
                if k == '_id':
                    if str(p.get('_id')) != str(v):
                        match = False
                        break
                elif p.get(k) != v:
                    match = False
                    break
            if match:
                return p
        return None

    def insert_one(self, doc):
        if '_id' not in doc:
            doc['_id'] = ObjectId()
        self.passes.append(doc)
        return doc

    def update_one(self, query, update):
        doc = self.find_one(query)
        if doc and '$set' in update:
            for k, v in update['$set'].items():
                doc[k] = v
        return doc

    def find_one_and_delete(self, query):
        doc = self.find_one(query)
        if doc:
            self.passes.remove(doc)
            return doc
        return None

# ── MongoDB connection ─────────────────────────────────────────────────────────
db_col = MockCollection()

def connect_db_async():
    global db_col
    if HAS_MONGO and MONGODB_URI and MONGODB_URI not in ('', 'YOUR_MONGODB_URI_HERE'):
        try:
            # Patch DNS inside the thread so it never blocks the main server startup
            try:
                import dns.resolver
                dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
                dns.resolver.default_resolver.nameservers = ['8.8.8.8', '8.8.4.4', '1.1.1.1']
                print("[INFO] DNS patched to Google/Cloudflare nameservers.", flush=True)
            except Exception as dns_err:
                print(f"[WARN] DNS patch skipped: {dns_err}", flush=True)

            print("[INFO] Connecting to MongoDB Atlas...", flush=True)
            client = MongoClient(
                MONGODB_URI,
                serverSelectionTimeoutMS=8000,
                connectTimeoutMS=8000,
                socketTimeoutMS=10000,
            )
            real_db_col = client['dtcpass']['passes']
            real_db_col.find_one({})  # Test connection
            db_col = real_db_col
            print("[OK] MongoDB Atlas connected successfully!", flush=True)
            _load_registration_setting()
        except Exception as e:
            print(f"[WARN] MongoDB connection failed: {e}", flush=True)
            print("[INFO] Falling back to in-memory mock database.", flush=True)
    else:
        print("[INFO] MONGODB_URI not set — using in-memory mock database.", flush=True)

import threading
threading.Thread(target=connect_db_async, daemon=True).start()

# ── Helpers ────────────────────────────────────────────────────────────────────

def generate_passno():
    return '750' + str(random.randint(1000000000, 9999999999))


def upload_to_imgbb(image_bytes: bytes) -> str:
    """Upload image bytes to ImgBB and return the public URL."""
    if not HAS_REQUESTS:
        raise RuntimeError("requests library not installed")
    if not IMGBB_API_KEY or IMGBB_API_KEY == 'YOUR_IMGBB_API_KEY_HERE':
        raise RuntimeError("ImgBB API key is missing in .env")
    encoded = base64.b64encode(image_bytes).decode('utf-8')
    resp = req_lib.post(
        f"https://api.imgbb.com/1/upload?key={IMGBB_API_KEY}",
        data={'image': encoded},
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()['data']['url']


def doc_to_dict(doc) -> dict:
    """Convert a MongoDB document to a JSON-serialisable dict."""
    if doc is None:
        return None
    d = dict(doc)
    # Convert ObjectId → string
    if '_id' in d:
        d['_id'] = str(d['_id'])
    # Convert datetime → ISO string
    for key in ('validFrom', 'validTo', 'createdAt', 'updatedAt'):
        if key in d and isinstance(d[key], datetime):
            d[key] = d[key].isoformat()
    return d


def parse_multipart(handler):
    """Parse multipart/form-data from the request body without using cgi or external packages."""
    ctype = handler.headers.get('Content-Type', '')
    length = int(handler.headers.get('Content-Length', 0))
    body = handler.rfile.read(length)

    fields = {}
    files = {}

    if not ctype.startswith('multipart/form-data'):
        return fields, files

    # Find the boundary
    boundary_marker = 'boundary='
    idx = ctype.find(boundary_marker)
    if idx == -1:
        return fields, files
    boundary = ctype[idx + len(boundary_marker):].strip()
    if not boundary:
        return fields, files

    # Split body by boundary (prefix with --)
    boundary_bytes = ('--' + boundary).encode('utf-8')
    parts = body.split(boundary_bytes)

    for part in parts:
        part = part.strip()
        if not part or part == b'--':
            continue

        # Split headers and content
        if b'\r\n\r\n' in part:
            header_bytes, content_bytes = part.split(b'\r\n\r\n', 1)
        elif b'\n\n' in part:
            header_bytes, content_bytes = part.split(b'\n\n', 1)
        else:
            continue

        # Trim trailing \r\n from content
        if content_bytes.endswith(b'\r\n'):
            content_bytes = content_bytes[:-2]
        elif content_bytes.endswith(b'\n'):
            content_bytes = content_bytes[:-1]

        # Parse headers
        headers = {}
        for line in header_bytes.decode('utf-8', errors='ignore').split('\n'):
            line = line.strip()
            if not line:
                continue
            if ':' in line:
                k, v = line.split(':', 1)
                headers[k.strip().lower()] = v.strip()

        # Parse Content-Disposition
        disposition = headers.get('content-disposition', '')
        if not disposition:
            continue

        params = {}
        for param in disposition.split(';'):
            if '=' in param:
                pk, pv = param.strip().split('=', 1)
                params[pk.strip().lower()] = pv.strip().strip('"')

        name = params.get('name')
        if not name:
            continue

        filename = params.get('filename')
        if filename is not None:
            # File field
            files[name] = content_bytes
        else:
            # Ordinary text field
            fields[name] = content_bytes.decode('utf-8', errors='ignore')

    return fields, files


# ── HTTP Handler ───────────────────────────────────────────────────────────────

class APIHandler(BaseHTTPRequestHandler):

    def address_string(self):
        return self.client_address[0]

    def _send_json(self, status: int, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.end_headers()
        self.wfile.write(body)

    def _path_and_query(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        # Flatten single-value lists
        qs = {k: (v[0] if len(v) == 1 else v) for k, v in qs.items()}
        return parsed.path.rstrip('/'), qs

    # CORS pre-flight
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    # ── GET ──────────────────────────────────────────────────────────────────
    def do_GET(self):
        path, qs = self._path_and_query()

        # GET / — Root route: only show "API Running" or error
        if path == '' or path == '/':
            try:
                # Quick check: if db_col is accessible, API is healthy
                _ = db_col
                return self._send_json(200, {'status': 'API Running'})
            except Exception as e:
                return self._send_json(500, {'error': str(e)})

        # GET /api/health — Used by cron-job.org to keep Render awake
        if path == '/api/health':
            now_ist = datetime.now(timezone.utc).strftime('%d/%m/%Y, %I:%M:%S %p')
            return self._send_json(200, {
                'status':  'OK',
                'time':    now_ist,
                'service': 'DTC e-Bus Pass Backend'
            })

        # GET /api/settings - retrieve global registration settings
        if path == '/api/settings':
            return self._send_json(200, {'allow_registration': ALLOW_REGISTRATION})

        # GET /api/passes  – list all (admin)
        if path == '/api/passes':
            if db_col is None:
                return self._send_json(500, {'error': 'Database not connected'})
            docs = list(db_col.find().sort('createdAt', -1))
            return self._send_json(200, [doc_to_dict(d) for d in docs])

        # GET /api/passes/check?mobile=&dob=
        if path == '/api/passes/check':
            mobile = qs.get('mobile', '').strip()
            dob    = qs.get('dob', '').strip()
            if not mobile or not dob:
                return self._send_json(400, {'error': 'Mobile and Date of Birth are required.'})
            if db_col is None:
                return self._send_json(500, {'error': 'Database not connected'})
            doc = db_col.find_one({'mobile': mobile, 'dob': dob})
            if doc:
                return self._send_json(200, {'exists': True, 'pass': doc_to_dict(doc)})
            return self._send_json(200, {'exists': False})

        # GET /api/passes/<passno>
        if path.startswith('/api/passes/'):
            passno = path[len('/api/passes/'):]
            if db_col is None:
                return self._send_json(500, {'error': 'Database not connected'})
            doc = db_col.find_one({'passno': passno})
            if not doc and passno == '7502032600973':
                # Fallback: Find the default Pawan Kumar record by its unique _id
                doc = db_col.find_one({'_id': ObjectId('6443c5b96912b7a4cf8a27d2')})
            if not doc:
                return self._send_json(404, {'error': 'Bus Pass not found.'})
            return self._send_json(200, doc_to_dict(doc))

        # GET /api/captcha — Generate a new captcha image (SVG) + token
        if path == '/api/captcha':
            token, text = generate_captcha_token()
            svg_bytes = draw_captcha_image(text)
            # Send SVG image
            self.send_response(200)
            self.send_header('Content-Type', 'image/svg+xml')
            self.send_header('Content-Length', str(len(svg_bytes)))
            self.send_header('X-Captcha-Token', token)  # token sent in header
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Expose-Headers', 'X-Captcha-Token')
            self.send_header('Cache-Control', 'no-store, no-cache')
            self.end_headers()
            self.wfile.write(svg_bytes)
            return

        self._send_json(404, {'error': 'Not found'})

    # ── POST ─────────────────────────────────────────────────────────────────
    def do_POST(self):
        path, _ = self._path_and_query()

        # POST /api/captcha/verify — Validate captcha token + user input
        if path == '/api/captcha/verify':
            try:
                length = int(self.headers.get('Content-Length', 0))
                data   = json.loads(self.rfile.read(length).decode('utf-8'))
                token  = data.get('token', '').strip()
                answer = data.get('answer', '').strip()
                if not token or not answer:
                    return self._send_json(400, {'error': 'token and answer required'})
                if verify_captcha_token(token, answer):
                    return self._send_json(200, {'valid': True})
                return self._send_json(200, {'valid': False, 'error': 'Wrong captcha. Please try again.'})
            except Exception as e:
                return self._send_json(400, {'error': str(e)})

        # POST /api/settings - toggle registration state (persisted to DB)
        if path == '/api/settings':
            global ALLOW_REGISTRATION
            try:
                length = int(self.headers.get('Content-Length', 0))
                body   = self.rfile.read(length).decode('utf-8')
                data   = json.loads(body)
                ALLOW_REGISTRATION = bool(data.get('allow_registration', True))
                _save_registration_setting(ALLOW_REGISTRATION)  # ← persist to MongoDB
                print(f"[INFO] Registration setting updated + saved to DB: {ALLOW_REGISTRATION}")
                return self._send_json(200, {'success': True, 'allow_registration': ALLOW_REGISTRATION})
            except Exception as e:
                return self._send_json(400, {'error': str(e)})

        # POST /api/passes/apply
        if path == '/api/passes/apply':
            if not ALLOW_REGISTRATION:
                return self._send_json(403, {'error': 'Registration is currently disabled by Admin.'})
            try:
                fields, files = parse_multipart(self)
                name   = fields.get('name', '').strip()
                mobile = fields.get('mobile', '').strip()
                dob    = fields.get('dob', '').strip()

                if not files.get('photo'):
                    return self._send_json(400, {'error': 'Please upload a photo.'})
                if db_col is None:
                    return self._send_json(500, {'error': 'Database not connected'})

                print("[INFO] Uploading photo to ImgBB...")
                photo_url = upload_to_imgbb(files['photo'])
                print(f"[INFO] Photo URL: {photo_url}")

                now      = datetime.now(timezone.utc)
                valid_to = now + timedelta(days=5*30 - 1)
                passno   = generate_passno()

                doc = {
                    'passno':   passno,
                    'name':     name.upper(),
                    'mobile':   mobile,
                    'dob':      dob,
                    'photoUrl': photo_url,
                    'qrCodeUrl': '',
                    'validFrom': now,
                    'validTo':  valid_to,
                    'createdAt': now,
                    'updatedAt': now,
                }
                db_col.insert_one(doc)
                print(f"[INFO] Saved pass {passno} to MongoDB.")

                return self._send_json(201, {
                    'success': True,
                    'passno': passno,
                    'redirectUrl': f'/viewEPass.html?passno={passno}'
                })
            except Exception as e:
                traceback.print_exc()
                return self._send_json(500, {'error': str(e)})

        self._send_json(405, {'error': 'Method Not Allowed'})

    # ── PUT ──────────────────────────────────────────────────────────────────
    def do_PUT(self):
        path, _ = self._path_and_query()

        # PUT /api/passes/<id>
        if path.startswith('/api/passes/'):
            pass_id = path[len('/api/passes/'):]
            try:
                fields, files = parse_multipart(self)

                if db_col is None:
                    return self._send_json(500, {'error': 'Database not connected'})

                doc = db_col.find_one({'_id': ObjectId(pass_id)})
                if not doc:
                    return self._send_json(404, {'error': 'Pass not found.'})

                update = {'updatedAt': datetime.now(timezone.utc)}

                if files.get('photo'):
                    update['photoUrl'] = upload_to_imgbb(files['photo'])
                if files.get('qrCode'):
                    update['qrCodeUrl'] = upload_to_imgbb(files['qrCode'])
                if fields.get('name'):    update['name']      = fields['name'].strip().upper()
                if fields.get('mobile'):  update['mobile']    = fields['mobile'].strip()
                if fields.get('dob'):     update['dob']       = fields['dob'].strip()
                if fields.get('passno'):  update['passno']    = fields['passno'].strip()
                if fields.get('validFrom'):
                    dt = datetime.fromisoformat(fields['validFrom'])
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    update['validFrom'] = dt
                if fields.get('validTo'):
                    dt = datetime.fromisoformat(fields['validTo'])
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    update['validTo'] = dt

                db_col.update_one({'_id': ObjectId(pass_id)}, {'$set': update})
                updated = db_col.find_one({'_id': ObjectId(pass_id)})
                print(f"[INFO] Pass successfully updated in database: {doc_to_dict(updated)}")
                return self._send_json(200, {'success': True, 'pass': doc_to_dict(updated)})

            except Exception as e:
                traceback.print_exc()
                return self._send_json(500, {'error': str(e)})

        self._send_json(404, {'error': 'Not found'})

    # ── DELETE ───────────────────────────────────────────────────────────────
    def do_DELETE(self):
        path, _ = self._path_and_query()

        if path.startswith('/api/passes/'):
            pass_id = path[len('/api/passes/'):]
            try:
                if db_col is None:
                    return self._send_json(500, {'error': 'Database not connected'})
                result = db_col.find_one_and_delete({'_id': ObjectId(pass_id)})
                if not result:
                    return self._send_json(404, {'error': 'Pass not found.'})
                return self._send_json(200, {'success': True, 'message': 'Pass deleted successfully.'})
            except Exception as e:
                traceback.print_exc()
                return self._send_json(500, {'error': str(e)})

        self._send_json(404, {'error': 'Not found'})

    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}")


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    try:
        print(f"[START] Binding HTTPServer to {HOST}:{PORT} ...", flush=True)
        server = HTTPServer((HOST, PORT), APIHandler)
        print(f"[OK] DTC API server is LIVE on http://{HOST}:{PORT}", flush=True)
        print("     Press Ctrl+C to stop.", flush=True)
        server.serve_forever()
    except OSError as e:
        print(f"[FATAL] Cannot bind to {HOST}:{PORT} - {e}", flush=True)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[INFO] API server stopped.")
    except Exception as e:
        print(f"[FATAL] Unexpected error: {e}", flush=True)
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)
