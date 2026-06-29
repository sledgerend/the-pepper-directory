import sqlite3
import os
import io
import csv
import json
from flask import Flask, request, jsonify, send_from_directory, Response

app = Flask(__name__, static_folder='public', static_url_path='')

DB_PATH = os.environ.get('DB_PATH', os.path.join(os.path.dirname(__file__), 'inventory.db'))
PORT = int(os.environ.get('PORT', 3000))
PAGE_SIZE = 50

# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA foreign_keys=ON')
    return db

def init_db():
    with get_db() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS posters (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT    NOT NULL,
                artist      TEXT    DEFAULT '',
                year        TEXT    DEFAULT '',
                category    TEXT    DEFAULT '',
                size        TEXT    DEFAULT '',
                condition   TEXT    DEFAULT '',
                quantity    INTEGER DEFAULT 1,
                location    TEXT    DEFAULT '',
                sku         TEXT    DEFAULT '',
                notes       TEXT    DEFAULT '',
                created_at  TEXT    DEFAULT (datetime('now')),
                updated_at  TEXT    DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_location ON posters(location);
            CREATE INDEX IF NOT EXISTS idx_category ON posters(category);
            CREATE INDEX IF NOT EXISTS idx_sku      ON posters(sku);
            CREATE INDEX IF NOT EXISTS idx_updated  ON posters(updated_at);

            CREATE VIRTUAL TABLE IF NOT EXISTS posters_fts USING fts5(
                title, artist, year, category, location, sku, notes,
                content='posters',
                content_rowid='id'
            );

            CREATE TRIGGER IF NOT EXISTS posters_ai AFTER INSERT ON posters BEGIN
                INSERT INTO posters_fts(rowid,title,artist,year,category,location,sku,notes)
                VALUES (new.id,new.title,new.artist,new.year,new.category,new.location,new.sku,new.notes);
            END;

            CREATE TRIGGER IF NOT EXISTS posters_ad AFTER DELETE ON posters BEGIN
                INSERT INTO posters_fts(posters_fts,rowid,title,artist,year,category,location,sku,notes)
                VALUES ('delete',old.id,old.title,old.artist,old.year,old.category,old.location,old.sku,old.notes);
            END;

            CREATE TRIGGER IF NOT EXISTS posters_au AFTER UPDATE ON posters BEGIN
                INSERT INTO posters_fts(posters_fts,rowid,title,artist,year,category,location,sku,notes)
                VALUES ('delete',old.id,old.title,old.artist,old.year,old.category,old.location,old.sku,old.notes);
                INSERT INTO posters_fts(rowid,title,artist,year,category,location,sku,notes)
                VALUES (new.id,new.title,new.artist,new.year,new.category,new.location,new.sku,new.notes);
            END;
        ''')

# ── Helpers ───────────────────────────────────────────────────────────────────

def row_to_dict(row):
    return dict(row) if row else None

def sanitize(body):
    return {
        'title':     (body.get('title', '') or '').strip(),
        'artist':    (body.get('artist', '') or '').strip(),
        'year':      str(body.get('year', '') or '').strip(),
        'category':  (body.get('category', '') or '').strip(),
        'size':      (body.get('size', '') or '').strip(),
        'condition': (body.get('condition', '') or '').strip(),
        'quantity':  int(body.get('quantity', 1) or 1),
        'location':  (body.get('location', '') or '').strip(),
        'sku':       (body.get('sku', '') or '').strip(),
        'notes':     (body.get('notes', '') or '').strip(),
    }

def build_fts_term(q):
    """Convert a plain query string to an FTS5 prefix query."""
    parts = q.strip().split()
    return ' '.join(f'"{w}"*' for w in parts if w)

# ── Static ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('public', 'index.html')

# ── Posters ───────────────────────────────────────────────────────────────────

@app.route('/api/posters')
def list_posters():
    q        = (request.args.get('q', '') or '').strip()
    category = (request.args.get('category', '') or '').strip()
    page     = max(1, int(request.args.get('page', 1) or 1))
    offset   = (page - 1) * PAGE_SIZE

    with get_db() as db:
        if q:
            term = build_fts_term(q)
            cat_clause = 'AND p.category = ?' if category else ''
            params_rows  = [term] + ([category] if category else []) + [PAGE_SIZE, offset]
            params_count = [term] + ([category] if category else [])
            rows  = db.execute(f'''
                SELECT p.* FROM posters_fts f
                JOIN posters p ON p.id = f.rowid
                WHERE posters_fts MATCH ? {cat_clause}
                ORDER BY rank
                LIMIT ? OFFSET ?
            ''', params_rows).fetchall()
            total = db.execute(f'''
                SELECT COUNT(*) FROM posters_fts f
                JOIN posters p ON p.id = f.rowid
                WHERE posters_fts MATCH ? {cat_clause}
            ''', params_count).fetchone()[0]
        else:
            cat_clause = 'WHERE category = ?' if category else ''
            params_rows  = ([category] if category else []) + [PAGE_SIZE, offset]
            params_count = [category] if category else []
            rows  = db.execute(f'''
                SELECT * FROM posters {cat_clause}
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
            ''', params_rows).fetchall()
            total = db.execute(f'SELECT COUNT(*) FROM posters {cat_clause}', params_count).fetchone()[0]

    import math
    return jsonify({
        'rows':  [dict(r) for r in rows],
        'total': total,
        'page':  page,
        'pages': math.ceil(total / PAGE_SIZE) if total else 1,
    })

@app.route('/api/posters/<int:pid>')
def get_poster(pid):
    with get_db() as db:
        row = db.execute('SELECT * FROM posters WHERE id = ?', (pid,)).fetchone()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(dict(row))

@app.route('/api/posters', methods=['POST'])
def create_poster():
    p = sanitize(request.get_json(force=True) or {})
    if not p['title']:
        return jsonify({'error': 'Title is required'}), 400
    with get_db() as db:
        cur = db.execute('''
            INSERT INTO posters (title,artist,year,category,size,condition,quantity,location,sku,notes)
            VALUES (:title,:artist,:year,:category,:size,:condition,:quantity,:location,:sku,:notes)
        ''', p)
        row = db.execute('SELECT * FROM posters WHERE id = ?', (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201

@app.route('/api/posters/<int:pid>', methods=['PUT'])
def update_poster(pid):
    with get_db() as db:
        existing = db.execute('SELECT id FROM posters WHERE id = ?', (pid,)).fetchone()
        if not existing:
            return jsonify({'error': 'Not found'}), 404
        p = sanitize(request.get_json(force=True) or {})
        if not p['title']:
            return jsonify({'error': 'Title is required'}), 400
        p['id'] = pid
        db.execute('''
            UPDATE posters SET
                title=:title, artist=:artist, year=:year, category=:category,
                size=:size, condition=:condition, quantity=:quantity,
                location=:location, sku=:sku, notes=:notes,
                updated_at=datetime('now')
            WHERE id=:id
        ''', p)
        row = db.execute('SELECT * FROM posters WHERE id = ?', (pid,)).fetchone()
    return jsonify(dict(row))

@app.route('/api/posters/<int:pid>/location', methods=['PATCH'])
def update_location(pid):
    with get_db() as db:
        existing = db.execute('SELECT id FROM posters WHERE id = ?', (pid,)).fetchone()
        if not existing:
            return jsonify({'error': 'Not found'}), 404
        loc = (request.get_json(force=True) or {}).get('location', '')
        loc = (loc or '').strip()
        db.execute("UPDATE posters SET location=?, updated_at=datetime('now') WHERE id=?", (loc, pid))
    return jsonify({'id': pid, 'location': loc})

@app.route('/api/posters/<int:pid>', methods=['DELETE'])
def delete_poster(pid):
    with get_db() as db:
        cur = db.execute('DELETE FROM posters WHERE id = ?', (pid,))
    if cur.rowcount == 0:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'deleted': True})

# ── Stats ─────────────────────────────────────────────────────────────────────

@app.route('/api/stats')
def stats():
    with get_db() as db:
        total    = db.execute('SELECT COUNT(*) FROM posters').fetchone()[0]
        qty      = db.execute('SELECT SUM(quantity) FROM posters').fetchone()[0] or 0
        no_loc   = db.execute("SELECT COUNT(*) FROM posters WHERE location='' OR location IS NULL").fetchone()[0]
        cats     = db.execute("""
            SELECT category, COUNT(*) AS count FROM posters
            WHERE category != '' GROUP BY category ORDER BY count DESC LIMIT 20
        """).fetchall()
        recent   = db.execute("""
            SELECT id, title, location, updated_at FROM posters
            WHERE location != '' ORDER BY updated_at DESC LIMIT 10
        """).fetchall()
    return jsonify({
        'total':         total,
        'totalQty':      qty,
        'noLocation':    no_loc,
        'categories':    [dict(r) for r in cats],
        'recentlyMoved': [dict(r) for r in recent],
    })

# ── CSV import ────────────────────────────────────────────────────────────────

@app.route('/api/import/csv', methods=['POST'])
def import_csv():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    f = request.files['file']
    try:
        text = f.read().decode('utf-8-sig')  # handle BOM
        reader = csv.DictReader(io.StringIO(text))
        headers = [h.lower().strip() for h in (reader.fieldnames or [])]

        def find_col(*names):
            for n in names:
                if n in headers:
                    return n
            return None

        title_col = find_col('title', 'name', 'poster')
        if not title_col:
            return jsonify({'error': 'CSV must have a "title" column'}), 400

        artist_col   = find_col('artist', 'author', 'publisher')
        year_col     = find_col('year', 'date')
        cat_col      = find_col('category', 'type', 'genre')
        size_col     = find_col('size', 'dimensions')
        cond_col     = find_col('condition', 'grade')
        qty_col      = find_col('quantity', 'qty', 'count', 'stock')
        loc_col      = find_col('location', 'loc', 'bin', 'shelf')
        sku_col      = find_col('sku', 'id', 'item_id', 'item id', 'barcode', 'upc')
        notes_col    = find_col('notes', 'description', 'desc', 'note')

        def get(row, col, default=''):
            if col is None:
                return default
            # DictReader lowercases from our header list but row keys are original
            # we need to match case-insensitively
            for k, v in row.items():
                if k.lower().strip() == col:
                    return (v or '').strip()
            return default

        imported = 0
        skipped  = 0
        with get_db() as db:
            insert = '''
                INSERT INTO posters (title,artist,year,category,size,condition,quantity,location,sku,notes)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            '''
            for row in reader:
                title = get(row, title_col)
                if not title:
                    skipped += 1
                    continue
                qty_raw = get(row, qty_col, '1')
                try:
                    qty = int(qty_raw) if qty_raw else 1
                except ValueError:
                    qty = 1
                db.execute(insert, (
                    title,
                    get(row, artist_col),
                    get(row, year_col),
                    get(row, cat_col),
                    get(row, size_col),
                    get(row, cond_col),
                    qty,
                    get(row, loc_col),
                    get(row, sku_col),
                    get(row, notes_col),
                ))
                imported += 1

        return jsonify({'imported': imported, 'skipped': skipped})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── CSV export ────────────────────────────────────────────────────────────────

@app.route('/api/export/csv')
def export_csv():
    cols = ['id','title','artist','year','category','size','condition','quantity','location','sku','notes','created_at','updated_at']
    with get_db() as db:
        rows = db.execute('SELECT * FROM posters ORDER BY id').fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(cols)
    for row in rows:
        writer.writerow([row[c] for c in cols])
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename="posters.csv"'}
    )

# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    import socket
    hostname = socket.gethostname()
    print(f'Poster inventory running at http://localhost:{PORT}')
    print(f'Database: {DB_PATH}')
    print(f'Share with your team: http://<your-ip>:{PORT}')
    app.run(host='0.0.0.0', port=PORT, debug=False)
