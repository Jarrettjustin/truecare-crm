from flask import Flask, render_template, request, jsonify, send_file, Response
import sqlite3, os, json
from datetime import datetime

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'capital_legacy.db')

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
    for col in ['state','resume_filename']:
        try: conn.execute(f'ALTER TABLE applicants ADD COLUMN {col} TEXT')
        except: pass
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
def index(): return render_template('index.html')

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
    rd = os.path.join(os.path.dirname(os.path.abspath(__file__)),'resumes'); os.makedirs(rd,exist_ok=True)
    fname = f'applicant_{aid}.pdf'; f.save(os.path.join(rd,fname))
    conn = get_db(); conn.execute('UPDATE applicants SET resume_filename=?,updated_at=? WHERE id=?',(fname,datetime.now().isoformat(),aid)); conn.commit(); conn.close()
    return jsonify({'status':'uploaded','filename':fname})

@app.route('/api/applicants/<int:aid>/resume', methods=['GET'])
def download_resume(aid):
    conn = get_db(); row = conn.execute('SELECT resume_filename,name FROM applicants WHERE id=?',(aid,)).fetchone(); conn.close()
    if not row or not row['resume_filename']: return jsonify({'error':'No resume'}),404
    fpath = os.path.join(os.path.dirname(os.path.abspath(__file__)),'resumes',row['resume_filename'])
    return send_file(fpath,as_attachment=True,download_name=f"{row['name'].replace(' ','_')}_Resume.pdf")

@app.route('/api/applicants/<int:aid>/resume/view', methods=['GET'])
def view_resume(aid):
    conn = get_db(); row = conn.execute('SELECT resume_filename FROM applicants WHERE id=?',(aid,)).fetchone(); conn.close()
    if not row or not row['resume_filename']: return jsonify({'error':'No resume'}),404
    fpath = os.path.join(os.path.dirname(os.path.abspath(__file__)),'resumes',row['resume_filename'])
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

@app.route('/api/import', methods=['POST'])
def import_data():
    try:
        data = request.json; applicants = data.get('applicants',[]); conn = get_db(); updated=0; created=0
        for a in applicants:
            ex = conn.execute('SELECT id FROM applicants WHERE name=? OR phone=?',(a.get('name',''),a.get('phone',''))).fetchone()
            if ex:
                conn.execute('UPDATE applicants SET interview_status=?,hired_status=?,justin_notes=?,chester_notes=?,start_date=?,resume_text=?,interview_time=?,updated_at=? WHERE id=?',
                    (a.get('interview_status','Not started'),a.get('hired_status','Not started'),a.get('justin_notes',''),a.get('chester_notes',''),a.get('start_date',''),a.get('resume_text',''),a.get('interview_time',''),datetime.now().isoformat(),ex['id'])); updated+=1
            else:
                conn.execute('INSERT INTO applicants (name,phone,email,interview_time,interview_status,hired_status,justin_notes,chester_notes,start_date,resume_text,source,position,state,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (a.get('name',''),a.get('phone',''),a.get('email',''),a.get('interview_time',''),a.get('interview_status','Not started'),a.get('hired_status','Not started'),a.get('justin_notes',''),a.get('chester_notes',''),a.get('start_date',''),a.get('resume_text',''),a.get('source',''),a.get('position',''),a.get('state',''),datetime.now().isoformat())); created+=1
        conn.commit(); conn.close(); return jsonify({'status':'ok','updated':updated,'created':created})
    except Exception as e: return jsonify({'error':str(e)}),400

init_db()
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5051))
    print(f"✅ Capital Legacy CRM running at http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
