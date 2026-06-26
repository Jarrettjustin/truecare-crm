from flask import Flask, render_template, request, jsonify, send_file, Response, abort
from flask_mail import Mail, Message
import sqlite3, os, json, io, csv, zipfile
from datetime import datetime

from fill_packet import fill_packet

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'capital_legacy.db')
TEMPLATE_PDF = os.path.join(BASE_DIR, 'onboarding_packet.pdf')   # the EXACT 31-page packet
SIGNED_DIR = os.path.join(BASE_DIR, 'signed')
RESUMES_DIR = os.path.join(BASE_DIR, 'resumes')

# Public base URL used to build the signing link in the email.
# Set PUBLIC_BASE_URL in Railway; falls back to the production URL.
PUBLIC_BASE_URL = os.environ.get(
    'PUBLIC_BASE_URL', 'https://truecare-crm-production.up.railway.app'
).rstrip('/')

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'hiring@equitycoresolutions.com'
app.config['MAIL_PASSWORD'] = os.environ.get('GOOGLE_APP_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = ('Andrew Cabrera', 'hiring@equitycoresolutions.com')

mail = Mail(app)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS applicants (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phone TEXT, email TEXT,
        interview_time TEXT, interview_status TEXT DEFAULT "Not started",
        hired_status TEXT DEFAULT "Not started", justin_notes TEXT, chester_notes TEXT,
        start_date TEXT, resume_text TEXT, resume_filename TEXT, source TEXT, position TEXT,
        state TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    # new columns for the onboarding / e-sign workflow
    for col in ['state', 'resume_filename', 'onboarding_status', 'signed_filename', 'signed_at']:
        try:
            conn.execute(f'ALTER TABLE applicants ADD COLUMN {col} TEXT')
        except Exception:
            pass
    conn.commit()
    count = conn.execute('SELECT COUNT(*) FROM applicants').fetchone()[0]
    if count == 0:
        applicants = [
            ('Brevyn Henderson','813-954-9649','','TC 3pm EST June 11th','Not started','Not started','','','Got instant releases\n10 states\nWas only with United\nWas working on his tax business, season is over now','','Indeed'),
            ('Melancia Stvictor','772-321-8193','','TC 4pm EST June 11th','Not started','Not started','','','FL - 10-15 states\n2026 AHIP certs\nJust got instant releases\nNot working right now','FL','Indeed'),
            ('Brandon Almonte','954-279-7755','','TC 5pm EST June 11th','Not started','Not started','','','Works with Progressive\nIn a training class for Medicare\nGetting stagnant / no room to grow / almost pushing 30\nExperience with inbound leads','FL','Indeed'),
            ('Anthony Tennyson','804-277-1275','atennyson03@outlook.com','TC 6pm EST June 11th','Not started','Not started','','','8 states\nWas doing life insurance this last year\nDid Medicare a year ago\nHas instant releases','','Indeed'),
            ('Jonathan Silverio','973-272-5692','silverio.jon12@gmail.com','TC 4pm EST June 12th','Not started','Not started','','','15-20 states\nNeeds to get instant releases\nJust exploring options\nCarriers: Horizon, United, Clover, Aetna, Amerigroup, WellCare\nMain focus is Final Expense / ACA, Medicare secondary','NJ','Indeed'),
        ]
        conn.executemany('INSERT INTO applicants (name,phone,email,interview_time,interview_status,hired_status,justin_notes,chester_notes,resume_text,state,source) VALUES (?,?,?,?,?,?,?,?,?,?,?)', applicants)
        conn.commit()
    conn.close()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/applicants', methods=['GET'])
def get_applicants():
    conn = get_db()
    q = 'SELECT * FROM applicants WHERE 1=1'; params = []
    fs = request.args.get('interview_status',''); fh = request.args.get('hired_status',''); sr = request.args.get('search','')
    if fs: q += ' AND interview_status=?'; params.append(fs)
    if fh: q += ' AND hired_status=?'; params.append(fh)
    if sr: q += ' AND (name LIKE ? OR phone LIKE ? OR email LIKE ?)'; params.extend([f'%{sr}%']*3)
    rows = conn.execute(q+' ORDER BY created_at DESC', params).fetchall()
    conn.close(); return jsonify([dict(r) for r in rows])


@app.route('/api/applicants', methods=['POST'])
def add_applicant():
    d = request.json; conn = get_db()
    cur = conn.execute('INSERT INTO applicants (name,phone,email,interview_time,interview_status,hired_status,justin_notes,chester_notes,start_date,resume_text,source,position,state,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (d.get('name',''),d.get('phone',''),d.get('email',''),d.get('interview_time',''),d.get('interview_status','Not started'),d.get('hired_status','Not started'),d.get('justin_notes',''),d.get('chester_notes',''),d.get('start_date',''),d.get('resume_text',''),d.get('source',''),d.get('position',''),d.get('state',''),datetime.now().isoformat()))
    conn.commit(); nid = cur.lastrowid; conn.close(); return jsonify({'id':nid,'status':'created'})


@app.route('/api/applicants/<int:aid>', methods=['GET'])
def get_applicant(aid):
    conn = get_db(); row = conn.execute('SELECT * FROM applicants WHERE id=?',(aid,)).fetchone(); conn.close()
    return jsonify(dict(row)) if row else (jsonify({'error':'Not found'}),404)


@app.route('/api/applicants/<int:aid>', methods=['PUT'])
def update_applicant(aid):
    d = request.json; conn = get_db(); fields=[]; params=[]
    for f in ['name','phone','email','interview_time','interview_status','hired_status','justin_notes','chester_notes','start_date','resume_text','source','position','state']:
        if f in d: fields.append(f'{f}=?'); params.append(d[f])
    fields.append('updated_at=?'); params.append(datetime.now().isoformat()); params.append(aid)
    conn.execute(f'UPDATE applicants SET {", ".join(fields)} WHERE id=?', params); conn.commit(); conn.close()
    return jsonify({'status':'updated'})


@app.route('/api/applicants/<int:aid>', methods=['DELETE'])
def delete_applicant(aid):
    conn = get_db(); conn.execute('DELETE FROM applicants WHERE id=?',(aid,)); conn.commit(); conn.close()
    return jsonify({'status':'deleted'})


@app.route('/api/applicants/<int:aid>/resume', methods=['POST'])
def upload_resume(aid):
    if 'resume' not in request.files: return jsonify({'error':'No file'}),400
    f = request.files['resume']
    if not f.filename.lower().endswith('.pdf'): return jsonify({'error':'PDF only'}),400
    rd = os.path.join(BASE_DIR,'resumes'); os.makedirs(rd,exist_ok=True)
    fname = f'applicant_{aid}.pdf'; f.save(os.path.join(rd,fname))
    conn = get_db(); conn.execute('UPDATE applicants SET resume_filename=?,updated_at=? WHERE id=?',(fname,datetime.now().isoformat(),aid)); conn.commit(); conn.close()
    return jsonify({'status':'uploaded','filename':fname})


@app.route('/api/applicants/<int:aid>/resume', methods=['GET'])
def download_resume(aid):
    conn = get_db(); row = conn.execute('SELECT resume_filename,name FROM applicants WHERE id=?',(aid,)).fetchone(); conn.close()
    if not row or not row['resume_filename']: return jsonify({'error':'No resume'}),404
    fpath = os.path.join(BASE_DIR,'resumes',row['resume_filename'])
    return send_file(fpath,as_attachment=True,download_name=f"{row['name'].replace(' ','_')}_Resume.pdf")


@app.route('/api/applicants/<int:aid>/resume/view', methods=['GET'])
def view_resume(aid):
    conn = get_db(); row = conn.execute('SELECT resume_filename FROM applicants WHERE id=?',(aid,)).fetchone(); conn.close()
    if not row or not row['resume_filename']: return jsonify({'error':'No resume'}),404
    fpath = os.path.join(BASE_DIR,'resumes',row['resume_filename'])
    return send_file(fpath,mimetype='application/pdf')


@app.route('/api/stats')
def get_stats():
    conn = get_db()
    s = {'total':conn.execute('SELECT COUNT(*) FROM applicants').fetchone()[0],
         'hired':conn.execute("SELECT COUNT(*) FROM applicants WHERE hired_status='Hired'").fetchone()[0],
         'interviewed':conn.execute("SELECT COUNT(*) FROM applicants WHERE interview_status='Interviewed'").fetchone()[0],
         'no_show':conn.execute("SELECT COUNT(*) FROM applicants WHERE interview_status='No show'").fetchone()[0],
         'missed':conn.execute("SELECT COUNT(*) FROM applicants WHERE interview_status='Missed'").fetchone()[0],
         'pending':conn.execute("SELECT COUNT(*) FROM applicants WHERE interview_status='Not started'").fetchone()[0]}
    conn.close(); return jsonify(s)


@app.route('/api/export')
def export_data():
    conn = get_db(); rows = conn.execute('SELECT * FROM applicants ORDER BY id').fetchall(); conn.close()
    return Response(json.dumps({'exported_at':datetime.now().isoformat(),'applicants':[dict(r) for r in rows]},indent=2),
        mimetype='application/json',headers={'Content-Disposition':'attachment; filename=capital-legacy-export.json'})


@app.route("/api/import", methods=["POST"])
def import_data():
    try:
        data = request.json; applicants = data.get("applicants",[]); conn = get_db()
        conn.execute("DELETE FROM applicants")
        for a in applicants:
            conn.execute("INSERT INTO applicants (id,name,phone,email,interview_time,interview_status,hired_status,justin_notes,chester_notes,start_date,resume_text,source,position,state,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (a.get("id"),a.get("name",""),a.get("phone",""),a.get("email",""),a.get("interview_time",""),a.get("interview_status","Not started"),a.get("hired_status","Not started"),a.get("justin_notes",""),a.get("chester_notes",""),a.get("start_date",""),a.get("resume_text",""),a.get("source",""),a.get("position",""),a.get("state",""),datetime.now().isoformat()))
        conn.commit(); conn.close(); return jsonify({"status":"ok","imported":len(applicants)})
    except Exception as e: return jsonify({"error":str(e)}),400


@app.route("/api/import-csv", methods=["POST"])
def import_csv():
    try:
        raw = request.get_data(as_text=True)
        reader = csv.DictReader(io.StringIO(raw))
        conn = get_db()
        conn.execute("DELETE FROM applicants")
        count = 0
        for row in reader:
            def g(k): return (row.get(k) or "").strip()
            conn.execute(
                "INSERT INTO applicants (name,phone,email,interview_time,interview_status,hired_status,justin_notes,chester_notes,start_date,resume_text,source,position,state,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (g("name"), g("phone"), g("email"), g("interview_time"),
                 g("interview_status") or "Not started",
                 g("hired_status") or "Not started",
                 g("justin_notes"), g("chester_notes"), g("start_date"),
                 g("resume_text"), g("source"), g("position"), g("state"),
                 datetime.now().isoformat()))
            count += 1
        conn.commit(); conn.close()
        return jsonify({"status": "ok", "imported": count})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ───────────────────────── DAILY BACKUP / EXPORT / PURGE (demo tools) ─────────────────────────

TEXT_COLS = ['id', 'name', 'email', 'phone', 'interview_time', 'interview_status',
             'hired_status', 'onboarding_status', 'start_date', 'source', 'position',
             'state', 'justin_notes', 'chester_notes']


def _crm_rows():
    conn = get_db()
    rows = conn.execute('SELECT * FROM applicants ORDER BY id').fetchall()
    conn.close()
    out = []
    for r in rows:
        keys = r.keys()
        out.append({c: (r[c] if c in keys else '') for c in TEXT_COLS})
    return out


def _crm_csv_string():
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(TEXT_COLS)
    for row in _crm_rows():
        w.writerow(['' if row[c] is None else row[c] for c in TEXT_COLS])
    return buf.getvalue()


def _add_dir_to_zip(zf, dir_path, arc_prefix):
    count = 0
    if os.path.isdir(dir_path):
        for fn in sorted(os.listdir(dir_path)):
            fp = os.path.join(dir_path, fn)
            if os.path.isfile(fp):
                zf.write(fp, arcname=f'{arc_prefix}/{fn}')
                count += 1
    return count


# Option A — lightweight agent text data (CSV by default, ?format=json supported)
@app.route('/api/export/crm-text')
def export_crm_text():
    fmt = request.args.get('format', 'csv').lower()
    stamp = datetime.now().strftime('%Y-%m-%d')
    if fmt == 'json':
        payload = {'exported_at': datetime.now().isoformat(), 'applicants': _crm_rows()}
        return Response(json.dumps(payload, indent=2), mimetype='application/json',
                        headers={'Content-Disposition': f'attachment; filename=truecare-crm-text-{stamp}.json'})
    return Response(_crm_csv_string(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename=truecare-crm-text-{stamp}.csv'})


# Option B — all documents (resumes + signed packets) as a single zip
@app.route('/api/export/all-documents')
def export_all_documents():
    stamp = datetime.now().strftime('%Y-%m-%d')
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, 'w', zipfile.ZIP_DEFLATED) as zf:
        n1 = _add_dir_to_zip(zf, RESUMES_DIR, 'resumes')
        n2 = _add_dir_to_zip(zf, SIGNED_DIR, 'signed_packets')
        if n1 + n2 == 0:
            zf.writestr('README.txt', 'No documents were stored at export time.')
    mem.seek(0)
    return send_file(mem, mimetype='application/zip', as_attachment=True,
                     download_name=f'truecare-documents-{stamp}.zip')


# Option C — master backup: text data + all documents in one zip
@app.route('/api/export/master-backup')
def export_master_backup():
    stamp = datetime.now().strftime('%Y-%m-%d')
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('crm_data.csv', _crm_csv_string())
        zf.writestr('crm_data.json', json.dumps(
            {'exported_at': datetime.now().isoformat(), 'applicants': _crm_rows()}, indent=2))
        _add_dir_to_zip(zf, RESUMES_DIR, 'resumes')
        _add_dir_to_zip(zf, SIGNED_DIR, 'signed_packets')
    mem.seek(0)
    return send_file(mem, mimetype='application/zip', as_attachment=True,
                     download_name=f'truecare-master-backup-{stamp}.zip')


# Daily maintenance purge — wipes applicant rows + all stored files
@app.route('/api/data/purge', methods=['POST'])
def purge_data():
    d = request.json or {}
    if not d.get('confirm'):
        return jsonify({'error': 'Confirmation flag required'}), 400
    # optional shared secret: set PURGE_TOKEN in Railway to require it
    token = os.environ.get('PURGE_TOKEN')
    if token and d.get('token') != token:
        return jsonify({'error': 'Invalid purge token'}), 403

    conn = get_db()
    conn.execute('DELETE FROM applicants')
    try:
        conn.execute("DELETE FROM sqlite_sequence WHERE name='applicants'")
    except Exception:
        pass
    conn.commit(); conn.close()

    deleted = 0
    for dpath in (RESUMES_DIR, SIGNED_DIR):
        if os.path.isdir(dpath):
            for fn in os.listdir(dpath):
                fp = os.path.join(dpath, fn)
                try:
                    if os.path.isfile(fp):
                        os.remove(fp); deleted += 1
                except Exception:
                    pass
    return jsonify({'status': 'purged', 'files_deleted': deleted})


# ───────────────────────────── ONBOARDING E-SIGN WORKFLOW ─────────────────────────────

@app.route('/api/applicants/<int:aid>/send-onboarding', methods=['POST'])
def send_onboarding_email(aid):
    """Send a clean, TrueCare-branded signature request (NOT a Dropbox lookalike)."""
    d = request.json or {}
    target_email = (d.get('email', '') or '').strip()
    if not target_email:
        return jsonify({'error': 'Email address is required'}), 400

    conn = get_db()
    row = conn.execute('SELECT name FROM applicants WHERE id=?', (aid,)).fetchone()
    if not row:
        conn.close(); return jsonify({'error': 'Applicant not found'}), 404
    agent_name = row['name'] or 'Agent'

    signing_link = f"{PUBLIC_BASE_URL}/sign/{aid}"
    sender_email = app.config['MAIL_DEFAULT_SENDER'][1]

    try:
        msg = Message(
            subject=f"Andrew Cabrera requested your signature: TrueCare Onboarding Docs",
            recipients=[target_email],
        )
        msg.html = f"""
<html>
<body style="font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;background:#f4f5f7;margin:0;padding:32px 16px;-webkit-font-smoothing:antialiased;">
  <table align="center" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;margin:0 auto;">
    <tr><td align="center" style="padding:8px 0 24px;">
      <span style="font-size:26px;font-weight:700;color:#0f5b6e;letter-spacing:-.5px;">True<span style="color:#5bb85b;">Care</span></span>
    </td></tr>
    <tr><td style="background:#ffffff;border:1px solid #e6e8eb;border-radius:8px;overflow:hidden;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr><td style="background:#f7f8fa;padding:28px 36px;border-bottom:1px solid #eceef1;">
          <div style="font-size:12px;font-weight:700;letter-spacing:.08em;color:#8a9099;text-transform:uppercase;">Action Requested</div>
          <p style="font-size:18px;color:#1f2937;line-height:1.5;margin:12px 0 22px;">
            <strong>Andrew Cabrera</strong> (<a href="mailto:{sender_email}" style="color:#1a73e8;text-decoration:none;">{sender_email}</a>) has requested your signature.
          </p>
          <a href="{signing_link}" target="_blank" rel="noopener"
             style="display:inline-block;background:#1a73e8;color:#ffffff;font-size:15px;font-weight:600;text-decoration:none;padding:13px 30px;border-radius:6px;">
            Review &amp; sign
          </a>
        </td></tr>
        <tr><td style="padding:26px 36px;">
          <div style="font-size:14px;color:#6b7280;margin-bottom:2px;">Document</div>
          <div style="font-size:15px;color:#1f2937;font-weight:600;margin-bottom:20px;">TrueCare Onboarding Docs &mdash; {agent_name}</div>
          <div style="font-size:13px;color:#6b7280;">Message from Andrew Cabrera (<a href="mailto:{sender_email}" style="color:#1a73e8;text-decoration:none;">{sender_email}</a>)</div>
        </td></tr>
      </table>
    </td></tr>
    <tr><td align="center" style="padding:18px 12px;">
      <p style="font-size:12px;color:#9aa0a6;line-height:1.5;margin:0;">
        Thanks, The TrueCare team<br>
        &#9888; To protect your information, please do not forward this email.
      </p>
    </td></tr>
  </table>
</body>
</html>
"""
        mail.send(msg)
        conn.execute('UPDATE applicants SET onboarding_status=?, updated_at=? WHERE id=?',
                     ('Sent', datetime.now().isoformat(), aid))
        conn.commit(); conn.close()
        return jsonify({'status': 'sent', 'message': f'Onboarding invitation sent to {target_email}.'})
    except Exception as e:
        conn.close()
        return jsonify({'error': f'SMTP Error: {str(e)}'}), 500


@app.route('/sign/<int:aid>')
def sign_portal(aid):
    """Public signing portal: renders the EXACT packet, fillable, with a 100% guard."""
    conn = get_db()
    row = conn.execute('SELECT id,name,email,signed_filename FROM applicants WHERE id=?', (aid,)).fetchone()
    conn.close()
    if not row:
        abort(404)
    return render_template('sign.html', aid=aid, agent_name=row['name'] or '',
                           already_signed=bool(row['signed_filename']))


@app.route('/api/sign/<int:aid>/submit', methods=['POST'])
def submit_signed(aid):
    d = request.json or {}
    conn = get_db()
    row = conn.execute('SELECT name,email FROM applicants WHERE id=?', (aid,)).fetchone()
    if not row:
        conn.close(); return jsonify({'error': 'Applicant not found'}), 404

    # Server-side completeness guard (don't trust the client alone)
    required = ['full_name', 'npn', 'init_2_13', 'init_exhibit']
    for f in required:
        if not (d.get(f) or '').strip():
            conn.close(); return jsonify({'error': f'Missing required field: {f}'}), 400
    if not d.get('signature'):
        conn.close(); return jsonify({'error': 'Signature is required'}), 400

    if not os.path.exists(TEMPLATE_PDF):
        conn.close(); return jsonify({'error': 'Onboarding packet template not found on server.'}), 500

    os.makedirs(SIGNED_DIR, exist_ok=True)
    out_name = f'applicant_{aid}_signed.pdf'
    out_path = os.path.join(SIGNED_DIR, out_name)

    ip = request.headers.get('X-Forwarded-For', request.remote_addr or '')
    ip = ip.split(',')[0].strip()
    meta = {
        'full_name': d.get('full_name', '').strip(),
        'email': row['email'] or '',
        'npn': d.get('npn', '').strip(),
        'timestamp': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'),
        'ip': ip,
        'aid': aid,
        'signature': d.get('signature'),
    }
    data = {
        'full_name': meta['full_name'],
        'npn': meta['npn'],
        'init_2_13': d.get('init_2_13', '').strip(),
        'init_exhibit': d.get('init_exhibit', '').strip(),
        'date': d.get('date') or datetime.utcnow().strftime('%m/%d/%Y'),
    }

    try:
        fill_packet(TEMPLATE_PDF, out_path, data, meta)
    except Exception as e:
        conn.close(); return jsonify({'error': f'PDF generation failed: {str(e)}'}), 500

    conn.execute('UPDATE applicants SET onboarding_status=?, signed_filename=?, signed_at=?, updated_at=? WHERE id=?',
                 ('Completed', out_name, datetime.now().isoformat(), datetime.now().isoformat(), aid))
    conn.commit(); conn.close()
    return jsonify({'status': 'completed'})


@app.route('/api/sign/<int:aid>/download', methods=['GET'])
def download_signed(aid):
    conn = get_db()
    row = conn.execute('SELECT name,signed_filename FROM applicants WHERE id=?', (aid,)).fetchone()
    conn.close()
    if not row or not row['signed_filename']:
        return jsonify({'error': 'No signed packet'}), 404
    fpath = os.path.join(SIGNED_DIR, row['signed_filename'])
    if not os.path.exists(fpath):
        return jsonify({'error': 'File missing on server'}), 404
    safe = (row['name'] or 'agent').replace(' ', '_')
    return send_file(fpath, as_attachment=True, download_name=f'{safe}_TrueCare_Signed_Packet.pdf')


init_db()
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5051))
    print(f"✅ TrueCare CRM running at http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
