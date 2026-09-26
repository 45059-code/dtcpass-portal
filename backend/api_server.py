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
    """Draw captcha text as SVG and return it as a base64 data URI string."""
    width, height = 200, 65
    chars = list(text)
    items = []
    colors = ['#c0392b','#2980b9','#27ae60','#8e44ad','#e67e22','#2c3e50']
    for i, ch in enumerate(chars):
        x = 18 + i * 29 + random.randint(-3, 3)
        y = 42 + random.randint(-6, 6)
        rot = random.randint(-15, 15)
        size = random.randint(24, 32)
        color = colors[i % len(colors)]
        items.append(
            f'<text x="{x}" y="{y}" transform="rotate({rot},{x},{y})" '
            f'font-size="{size}" font-family="Arial,monospace" font-weight="bold" '
            f'fill="{color}">{ch}</text>'
        )
    # Noise lines
    lines = []
    for _ in range(4):
        x1,y1 = random.randint(0,width), random.randint(0,height)
        x2,y2 = random.randint(0,width), random.randint(0,height)
        c = random.choice(['#bdc3c7','#95a5a6','#aab7b8'])
        lines.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{c}" stroke-width="1.5"/>')
    # Noise dots
    dots = []
    for _ in range(25):
        cx,cy = random.randint(0,width), random.randint(0,height)
        dots.append(f'<circle cx="{cx}" cy="{cy}" r="1.5" fill="#bdc3c7"/>')
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'style="background:#f4f6f7;border-radius:8px;">'
        + ''.join(lines) + ''.join(dots) + ''.join(items)
        + '</svg>'
    )
    svg_bytes = svg.encode('utf-8')
    # Return both raw bytes AND a data URI (used by /api/captcha/image)
    data_uri = 'data:image/svg+xml;base64,' + base64.b64encode(svg_bytes).decode('ascii')
    return svg_bytes, data_uri

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
_real_db = None  # holds the actual pymongo Database object when connected

def get_settings_collection():
    """Helper to safely get settings collection for both real PyMongo and MockCollection."""
    global db_col, _real_db
    if isinstance(db_col, MockCollection):
        # Use the MockCollection itself as the settings store
        # Build a thin adapter so the API is the same as real pymongo
        _mock_col = db_col  # capture reference
        class _MockSettingsCol:
            def find_one(self, query):
                if query.get('_id') == 'registration':
                    return _mock_col.settings_store.get('registration')
                return None
            def update_one(self, query, update, upsert=False):
                if query.get('_id') == 'registration' and '$set' in update:
                    if 'registration' not in _mock_col.settings_store:
                        _mock_col.settings_store['registration'] = {'_id': 'registration'}
                    _mock_col.settings_store['registration'].update(update['$set'])
                return None
        return _MockSettingsCol()

    # Real MongoDB path: use the stored database reference
    if _real_db is not None:
        try:
            return _real_db['settings']
        except Exception as e:
            print(f"[WARN] Error accessing settings collection: {e}", flush=True)
    return None

def _load_registration_setting():
    """Read allow_registration from MongoDB settings collection."""
    global ALLOW_REGISTRATION
    try:
        col = get_settings_collection()
        if col is not None:
            doc = col.find_one({'_id': 'registration'})
            if doc:
                ALLOW_REGISTRATION = bool(doc.get('allow_registration', True))
                print(f"[INFO] Loaded registration setting from DB: {ALLOW_REGISTRATION}", flush=True)
            else:
                print("[INFO] No registration setting found in DB, using default (True)", flush=True)
    except Exception as e:
        print(f"[WARN] Could not load registration setting from DB: {e}", flush=True)

def _save_registration_setting(value):
    """Persist allow_registration to MongoDB settings collection.
    
    NOTE: This always succeeds — if the DB collection is unavailable,
    the value is kept in memory only (ALLOW_REGISTRATION global) and a
    warning is printed. This prevents the frontend toggle from reverting.
    """
    try:
        col = get_settings_collection()
        if col is not None:
            col.update_one(
                {'_id': 'registration'},
                {'$set': {'allow_registration': value}},
                upsert=True
            )
            print(f"[INFO] Saved registration setting to DB: {value}", flush=True)
        else:
            # DB not ready yet — value is already updated in ALLOW_REGISTRATION global,
            # so the setting is still effective for this server session.
            print(f"[WARN] Settings collection unavailable — value saved in memory only: {value}", flush=True)
    except Exception as e:
        # Don't re-raise — the global is already updated so the toggle worked.
        print(f"[WARN] Could not persist registration setting to DB: {e}", flush=True)

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

PASSES_DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'passes_db.json')
CLOUD_API_URL  = 'https://dtcpass-backend-api.onrender.com'

class MockCollection:
    def __init__(self):
        self.passes = []
        self.settings_store = {'registration': {'allow_registration': True}}
        self.db_file = PASSES_DB_FILE
        self._load_from_disk()

        # Seed if empty
        if not self.passes:
            now = datetime.now(timezone.utc)
            self.passes.append({
                '_id': '6443c5b96912b7a4cf8a27d2',
                'passno': '7502032600973',
                'name': 'PAWAN KUMAR',
                'mobile': '8010106194',
                'dob': '09/05/2005',
                'photoUrl': 'https://i.ibb.co/0pxWFxwL/34a72bd2efb4.jpg',
                'qrCodeUrl': '',
                'validFrom': '2026-05-19T00:00:00',
                'validTo': '2026-10-18T00:00:00',
                'createdAt': '2026-05-19T00:00:00',
                'updatedAt': '2026-09-26T00:00:00',
            })
            self.save_to_disk()

        # Sync cloud in background
        import threading
        threading.Thread(target=self.sync_with_cloud, daemon=True).start()

    def _load_from_disk(self):
        try:
            if os.path.exists(self.db_file):
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.passes = data.get('passes', [])
                    self.settings_store = data.get('settings', {'registration': {'allow_registration': True}})
                elif isinstance(data, list):
                    self.passes = data
                print(f"[BOOT] Loaded {len(self.passes)} passes from {self.db_file}", flush=True)
        except Exception as e:
            print(f"[WARN] Failed to load {self.db_file}: {e}", flush=True)

    def save_to_disk(self):
        try:
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'passes': [doc_to_dict(p) for p in self.passes],
                    'settings': self.settings_store
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[WARN] Failed to save {self.db_file}: {e}", flush=True)

    def sync_with_cloud(self):
        if not HAS_REQUESTS:
            return
        try:
            resp = req_lib.get(f"{CLOUD_API_URL}/api/passes", timeout=8)
            if resp.status_code == 200:
                cloud_passes = resp.json()
                if isinstance(cloud_passes, list) and cloud_passes:
                    existing_passnos = {p.get('passno') for p in self.passes if p.get('passno')}
                    existing_ids = {str(p.get('_id')) for p in self.passes if p.get('_id')}
                    updated = False
                    for cp in cloud_passes:
                        pno = cp.get('passno')
                        cid = str(cp.get('_id'))
                        if pno not in existing_passnos and cid not in existing_ids:
                            self.passes.append(cp)
                            existing_passnos.add(pno)
                            existing_ids.add(cid)
                            updated = True
                    if updated:
                        print(f"[INFO] Cloud sync: updated local database to {len(self.passes)} passes.", flush=True)
                        self.save_to_disk()
        except Exception as e:
            print(f"[INFO] Cloud sync note: {e}", flush=True)

    def fetch_pass_from_cloud(self, passno):
        if not HAS_REQUESTS:
            return None
        try:
            resp = req_lib.get(f"{CLOUD_API_URL}/api/passes/{passno}", timeout=6)
            if resp.status_code == 200:
                doc = resp.json()
                if doc and doc.get('passno'):
                    if not any(p.get('passno') == doc.get('passno') for p in self.passes):
                        self.passes.append(doc)
                        self.save_to_disk()
                    return doc
        except Exception:
            pass
        return None

    def check_pass_from_cloud(self, mobile, dob):
        if not HAS_REQUESTS:
            return None
        try:
            import urllib.parse
            q = urllib.parse.urlencode({'mobile': mobile, 'dob': dob})
            resp = req_lib.get(f"{CLOUD_API_URL}/api/passes/check?{q}", timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('exists') and data.get('pass'):
                    doc = data['pass']
                    if not any(p.get('passno') == doc.get('passno') for p in self.passes):
                        self.passes.append(doc)
                        self.save_to_disk()
                    return doc
        except Exception:
            pass
        return None

    def find(self, query=None):
        results = list(self.passes)
        class Cursor:
            def __init__(self, data):
                self.data = data
            def sort(self, key, direction=1):
                if key == 'createdAt' and direction == -1:
                    def sort_key(x):
                        val = x.get('createdAt')
                        if isinstance(val, datetime):
                            return val.isoformat()
                        return str(val or '')
                    return sorted(self.data, key=sort_key, reverse=True)
                return self.data
            def __iter__(self):
                return iter(self.data)
        return Cursor(results)

    def find_one(self, query):
        if query.get('_id') == 'registration':
            return self.settings_store.get('registration')
        for p in self.passes:
            match = True
            for k, v in query.items():
                if k == '_id':
                    if str(p.get('_id')) != str(v):
                        match = False
                        break
                elif str(p.get(k, '')).strip() != str(v).strip():
                    match = False
                    break
            if match:
                return p
        return None

    def insert_one(self, doc):
        if '_id' not in doc:
            doc['_id'] = str(ObjectId())
        self.passes.append(doc)
        self.save_to_disk()
        return doc

    def update_one(self, query, update):
        if query.get('_id') == 'registration':
            if '$set' in update:
                self.settings_store['registration'].update(update['$set'])
                self.save_to_disk()
            return self.settings_store['registration']
        doc = self.find_one(query)
        if doc and '$set' in update:
            for k, v in update['$set'].items():
                doc[k] = v
            self.save_to_disk()
        return doc

    def find_one_and_delete(self, query):
        doc = self.find_one(query)
        if doc:
            self.passes.remove(doc)
            self.save_to_disk()
            return doc
        return None

# ── MongoDB connection ─────────────────────────────────────────────────────────
db_col = MockCollection()

def connect_db_async():
    global db_col, _real_db  # ← CRITICAL: must declare _real_db as global here
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
            real_db = client['dtcpass']
            real_db_col = real_db['passes']
            real_db_col.find_one({})  # Test connection
            db_col = real_db_col
            _real_db = real_db  # ← NOW correctly sets the global (not a local variable)
            print("[OK] MongoDB Atlas connected successfully!", flush=True)
            _load_registration_setting()  # ← now works because _real_db is set globally
        except Exception as e:
            print(f"[WARN] MongoDB connection failed: {e}", flush=True)
            print("[INFO] Falling back to local mock database with disk persistence.", flush=True)
    else:
        print("[INFO] MONGODB_URI not set — using local mock database with disk persistence.", flush=True)

import threading
threading.Thread(target=connect_db_async, daemon=True).start()

# ── Helpers ────────────────────────────────────────────────────────────────────

def generate_passno():
    return '750' + str(random.randint(1000000000, 9999999999))


def _compress_image(image_bytes: bytes, max_bytes: int = 1_400_000) -> bytes:
    """Compress/resize image so it is under max_bytes. Returns JPEG bytes."""
    try:
        from PIL import Image as PILImage
        import io
        img = PILImage.open(io.BytesIO(image_bytes))
        # Convert RGBA/P to RGB for JPEG compatibility
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')
        quality = 85
        while quality >= 30:
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=quality, optimize=True)
            compressed = buf.getvalue()
            if len(compressed) <= max_bytes:
                return compressed
            quality -= 10
        # If still too large, also halve dimensions
        w, h = img.size
        img = img.resize((w // 2, h // 2), PILImage.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=50, optimize=True)
        return buf.getvalue()
    except Exception as ce:
        print(f"[WARN] PIL compression failed ({ce}), returning original bytes", flush=True)
        return image_bytes


def upload_to_imgbb(image_bytes: bytes) -> str:
    """Upload image bytes to ImgBB and return public URL, with data URI fallback."""
    if not IMGBB_API_KEY or IMGBB_API_KEY == 'YOUR_IMGBB_API_KEY_HERE' or not HAS_REQUESTS:
        return 'data:image/jpeg;base64,' + base64.b64encode(image_bytes).decode('utf-8')
    try:
        # Compress image to stay within ImgBB's 32 MB limit (safe at <1.5 MB raw)
        compressed = _compress_image(image_bytes)
        encoded = base64.b64encode(compressed).decode('utf-8')
        resp = req_lib.post(
            'https://api.imgbb.com/1/upload',
            params={'key': IMGBB_API_KEY},
            data={'image': encoded},
            timeout=30
        )
        if not resp.ok:
            print(f"[WARN] ImgBB returned HTTP {resp.status_code}: {resp.text[:200]}", flush=True)
        resp.raise_for_status()
        return resp.json()['data']['url']
    except Exception as e:
        print(f"[WARN] ImgBB upload failed ({e}), using inline data URI fallback", flush=True)
        return 'data:image/jpeg;base64,' + base64.b64encode(image_bytes).decode('utf-8')


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
        self.close_connection = True
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Connection', 'close')
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
        self.close_connection = True
        self.send_response(204)
        self.send_header('Connection', 'close')
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
                db_type = 'Mock' if isinstance(db_col, MockCollection) else 'MongoDB Atlas'
                return self._send_json(200, {'status': 'API Running', 'database': db_type})
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
            if isinstance(db_col, MockCollection) and len(db_col.passes) <= 1:
                db_col.sync_with_cloud()
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
            if not doc and isinstance(db_col, MockCollection):
                doc = db_col.check_pass_from_cloud(mobile, dob)
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
                # Fallback: Find the default demo record by its unique _id
                doc = db_col.find_one({'_id': '6443c5b96912b7a4cf8a27d2'}) or db_col.find_one({'passno': '7502032600973'})
            if not doc and isinstance(db_col, MockCollection):
                doc = db_col.fetch_pass_from_cloud(passno)
            if not doc:
                return self._send_json(404, {'error': 'Bus Pass not found.'})
            return self._send_json(200, doc_to_dict(doc))

        # GET /api/captcha — Generate a new captcha image (SVG binary) + token
        # NOTE: Prefer /api/captcha/image for frontend (avoids blob URL race condition)
        if path == '/api/captcha':
            token, text = generate_captcha_token()
            svg_bytes, data_uri = draw_captcha_image(text)
            # Send SVG image
            self.close_connection = True
            self.send_response(200)
            self.send_header('Content-Type', 'image/svg+xml')
            self.send_header('Content-Length', str(len(svg_bytes)))
            self.send_header('Connection', 'close')
            self.send_header('X-Captcha-Token', token)  # token sent in header
            self.send_header('X-Captcha-DataUri', data_uri)  # data URI for convenience
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Expose-Headers', 'X-Captcha-Token,X-Captcha-DataUri')
            self.send_header('Cache-Control', 'no-store, no-cache')
            self.end_headers()
            self.wfile.write(svg_bytes)
            return

        # GET /api/captcha/image — Returns JSON {token, dataUri} atomically (no race condition)
        # This is the PREFERRED endpoint for frontend use.
        if path == '/api/captcha/image':
            token, text = generate_captcha_token()
            svg_bytes, data_uri = draw_captcha_image(text)
            return self._send_json(200, {'token': token, 'dataUri': data_uri})

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
                    'redirectUrl': f'/viewEBPass.html?passno={passno}'
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

                try:
                    query_id = ObjectId(pass_id)
                except Exception:
                    query_id = pass_id
                db_col.update_one({'_id': query_id}, {'$set': update})
                updated = db_col.find_one({'_id': query_id})
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
                try:
                    query_id = ObjectId(pass_id)
                except Exception:
                    query_id = pass_id
                result = db_col.find_one_and_delete({'_id': query_id})
                if not result:
                    return self._send_json(404, {'error': 'Pass not found.'})
                return self._send_json(200, {'success': True, 'message': 'Pass deleted successfully.'})
            except Exception as e:
                traceback.print_exc()
                return self._send_json(500, {'error': str(e)})

        self._send_json(404, {'error': 'Not found'})

    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}")


# ── Self keep-alive thread (prevents Render free-tier from sleeping) ────────────
def _keep_alive_loop():
    """
    Pings /api/health on the production Render URL every 14 minutes so
    Render's free-tier never idles.  Runs as a daemon thread; no output
    is shown on the frontend — purely a background operation.
    """
    import time as _time
    RENDER_URL = 'https://dtcpass-backend-api.onrender.com/api/health'
    INTERVAL   = 14 * 60  # 14 minutes (Render sleeps after 15 min of inactivity)
    _time.sleep(30)       # Wait 30 s after boot before first ping
    while True:
        try:
            if HAS_REQUESTS:
                r = req_lib.get(RENDER_URL, timeout=20)
                print(f"[KEEPALIVE] Pinged {RENDER_URL} -> HTTP {r.status_code}", flush=True)
        except Exception as _ke:
            print(f"[KEEPALIVE] Ping failed: {_ke}", flush=True)
        _time.sleep(INTERVAL)


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    # Start self keep-alive background thread
    import threading as _threading
    _ka_thread = _threading.Thread(target=_keep_alive_loop, daemon=True, name='KeepAlive')
    _ka_thread.start()
    print("[INFO] Keep-alive thread started (14-min interval)", flush=True)

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
