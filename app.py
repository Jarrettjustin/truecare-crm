from flask import Flask, render_template, request, jsonify, send_file
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'crm.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS applicants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            interview_time TEXT,
            interview_status TEXT DEFAULT 'Not started',
            hired_status TEXT DEFAULT 'Not started',
            justin_notes TEXT,
            chester_notes TEXT,
            start_date TEXT,
            resume_text TEXT,
            resume_filename TEXT,
            source TEXT,
            position TEXT,
            state TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    for col in ['state', 'resume_filename']:
        try:
            conn.execute(f'ALTER TABLE applicants ADD COLUMN {col} TEXT')
        except:
            pass
    conn.commit()

    # Seed data if empty
    count = conn.execute('SELECT COUNT(*) FROM applicants').fetchone()[0]
    if count == 0:
        applicants = [
            ('JACOB ELLIS', '407-402-5582', 'ellisjacob407@gmail.com', 'TC 10am June 11th', 'Not started', 'Not started', '', '', '', 'FL', 'Indeed'),
            ('Shameka Gardner', '786-862-3060', 'shamekafoster28@gmail.com', 'TC 4pm June 11th', 'Not started', 'Not started', '', '', '', 'FL', 'Indeed'),
            ('Shavanay Buckles', '256-289-4464', 'Shavbuckles12@gmail.com', 'TC 5pm June 11th', 'Not started', 'Not started', '', '', '', 'AL', 'Indeed'),
            ('L Mark Steinberg', '210-573-1319', '', 'TC 10:30am EST June 12th', 'Not started', 'Not started', '', '', '', 'TX', 'Indeed'),
            ('Shannon Sledd', '214-766-6890', 'Shannonc196@gmail.com', 'TC 4:30pm EST June 12th', 'Not started', 'Not started', '', '', '', 'TX', 'Indeed'),
            ('Ross Hanna', '843-877-7126', 'lifedirections2021@gmail.com', 'TC 5:30pm EST June 12th', 'Not started', 'Not started', '', '', '37 states licensed | NPN: 20087376 | ACA experience with BCBS', 'WV', 'Indeed'),
            ('Alexandria Navejas', '623-308-6866', 'lx52795@gmail.com', 'TC 1pm EST June 13th', 'Not started', 'Not started', '', '', '26 states licensed | Left eHealth, waiting for releases | No ACA experience', 'AZ', 'Indeed'),
            ('Dontressa Ashford', '704-949-6344', 'dcashford3@gmail.com', 'TC 3pm EST June 13th', 'Not started', 'Not started', '', '', '50 states licensed | Company shut down Dec 1st', 'NC', 'Indeed'),
            ('Gary Blackmon', '530-953-7104', 'garyblackmon@insurelife.life', 'TC 12:30pm EST June 15th', 'Not started', 'Not started', '', '', '35 states licensed | Has sold ACA in past | Lives in CA', 'CA', 'Indeed'),
            ('Avelino (Avy) Gonzalez', '561-699-3179', '', 'TC 10:30am EST June 16th', 'Not started', 'Not started', '', '', '5 states licensed | With Humana Presidents Club | Wants to leave Humana', 'TN', 'Indeed'),
        ]
        conn.executemany('''
            INSERT INTO applicants (name, phone, email, interview_time, interview_status, hired_status,
                justin_notes, chester_notes, resume_text, state, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', applicants)
        conn.commit()
    conn.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/applicants', methods=['GET'])
def get_applicants():
    conn = get_db()
    filter_status = request.args.get('interview_status', '')
    filter_hired = request.args.get('hired_status', '')
    search = request.args.get('search', '')
    query = 'SELECT * FROM applicants WHERE 1=1'
    params = []
    if filter_status:
        query += ' AND interview_status = ?'; params.append(filter_status)
    if filter_hired:
        query += ' AND hired_status = ?'; params.append(filter_hired)
    if search:
        query += ' AND (name LIKE ? OR phone LIKE ? OR email LIKE ?)'
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
    query += ' ORDER BY created_at DESC'
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/applicants', methods=['POST'])
def add_applicant():
    data = request.json
    conn = get_db()
    cur = conn.execute('''
        INSERT INTO applicants (name, phone, email, interview_time, interview_status, hired_status,
            justin_notes, chester_notes, start_date, resume_text, source, position, state, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (data.get('name',''), data.get('phone',''), data.get('email',''),
          data.get('interview_time',''), data.get('interview_status','Not started'),
          data.get('hired_status','Not started'), data.get('justin_notes',''),
          data.get('chester_notes',''), data.get('start_date',''), data.get('resume_text',''),
          data.get('source',''), data.get('position',''), data.get('state',''),
          datetime.now().isoformat()))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return jsonify({'id': new_id, 'status': 'created'})

@app.route('/api/applicants/<int:applicant_id>', methods=['GET'])
def get_applicant(applicant_id):
    conn = get_db()
    row = conn.execute('SELECT * FROM applicants WHERE id = ?', (applicant_id,)).fetchone()
    conn.close()
    if row is None:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(dict(row))

@app.route('/api/applicants/<int:applicant_id>', methods=['PUT'])
def update_applicant(applicant_id):
    data = request.json
    conn = get_db()
    fields, params = [], []
    updatable = ['name','phone','email','interview_time','interview_status','hired_status',
                 'justin_notes','chester_notes','start_date','resume_text','source','position','state']
    for f in updatable:
        if f in data:
            fields.append(f'{f} = ?'); params.append(data[f])
    fields.append('updated_at = ?'); params.append(datetime.now().isoformat())
    params.append(applicant_id)
    conn.execute(f'UPDATE applicants SET {", ".join(fields)} WHERE id = ?', params)
    conn.commit()
    conn.close()
    return jsonify({'status': 'updated'})

@app.route('/api/applicants/<int:applicant_id>', methods=['DELETE'])
def delete_applicant(applicant_id):
    conn = get_db()
    conn.execute('DELETE FROM applicants WHERE id = ?', (applicant_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'deleted'})

@app.route('/api/stats', methods=['GET'])
def get_stats():
    conn = get_db()
    total       = conn.execute('SELECT COUNT(*) FROM applicants').fetchone()[0]
    hired       = conn.execute("SELECT COUNT(*) FROM applicants WHERE hired_status = 'Hired'").fetchone()[0]
    interviewed = conn.execute("SELECT COUNT(*) FROM applicants WHERE interview_status = 'Interviewed'").fetchone()[0]
    no_show     = conn.execute("SELECT COUNT(*) FROM applicants WHERE interview_status = 'No show'").fetchone()[0]
    missed      = conn.execute("SELECT COUNT(*) FROM applicants WHERE interview_status = 'Missed'").fetchone()[0]
    pending     = conn.execute("SELECT COUNT(*) FROM applicants WHERE interview_status = 'Not started'").fetchone()[0]
    conn.close()
    return jsonify({'total': total, 'hired': hired, 'interviewed': interviewed,
                    'no_show': no_show, 'pending': pending, 'missed': missed})

init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    print(f"✅ Equity Core CRM running at http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
