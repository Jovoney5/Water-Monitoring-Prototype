from flask import Flask, request, jsonify, session, redirect, url_for, render_template_string, render_template
from flask_socketio import SocketIO, emit, join_room, leave_room
import sqlite3
import hashlib
from datetime import datetime, date
import json
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'water-monitoring-secret-key-2024'
socketio = SocketIO(app, cors_allowed_origins="*")

DATABASE = 'water_monitoring.db'

def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('inspector', 'admin')),
            full_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Water supplies table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS water_supplies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL CHECK (type IN ('treated', 'untreated')),
            agency TEXT NOT NULL,
            location TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Monthly supply data table for accumulative reporting
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS monthly_supply_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supply_id INTEGER NOT NULL,
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            visits INTEGER DEFAULT 0,
            chlorine_total INTEGER DEFAULT 0,
            chlorine_positive INTEGER DEFAULT 0,
            chlorine_negative INTEGER DEFAULT 0,
            bacteriological_positive INTEGER DEFAULT 0,
            bacteriological_negative INTEGER DEFAULT 0,
            bacteriological_pending INTEGER DEFAULT 0,
            remarks TEXT,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (supply_id) REFERENCES water_supplies (id),
            UNIQUE(supply_id, month, year)
        )
    ''')

    # Inspection submissions table for individual submissions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inspection_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supply_id INTEGER NOT NULL,
            inspector_id INTEGER NOT NULL,
            submission_date DATE NOT NULL,
            visits INTEGER DEFAULT 0,
            chlorine_total INTEGER DEFAULT 0,
            chlorine_positive INTEGER DEFAULT 0,
            chlorine_negative INTEGER DEFAULT 0,
            bacteriological_positive INTEGER DEFAULT 0,
            bacteriological_negative INTEGER DEFAULT 0,
            bacteriological_pending INTEGER DEFAULT 0,
            remarks TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (supply_id) REFERENCES water_supplies (id),
            FOREIGN KEY (inspector_id) REFERENCES users (id)
        )
    ''')

    # Insert default users
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        # Test users for demo/testing phase
        test_users = [
            # Admins (password: admin123)
            ('admin', hashlib.sha256('admin123'.encode()).hexdigest(), 'admin', 'System Administrator'),
            ('admin2', hashlib.sha256('admin123'.encode()).hexdigest(), 'admin', 'Senior Administrator'),

            # Inspectors (password: inspector123)
            ('inspector', hashlib.sha256('inspector123'.encode()).hexdigest(), 'inspector', 'Water Quality Inspector'),
            ('inspector1', hashlib.sha256('inspector123'.encode()).hexdigest(), 'inspector', 'Field Inspector A'),
            ('inspector2', hashlib.sha256('inspector123'.encode()).hexdigest(), 'inspector', 'Field Inspector B'),
            ('inspector3', hashlib.sha256('inspector123'.encode()).hexdigest(), 'inspector', 'Field Inspector C'),
            ('inspector4', hashlib.sha256('inspector123'.encode()).hexdigest(), 'inspector', 'Field Inspector D'),
            ('inspector5', hashlib.sha256('inspector123'.encode()).hexdigest(), 'inspector', 'Field Inspector E'),
            ('inspector6', hashlib.sha256('inspector123'.encode()).hexdigest(), 'inspector', 'Field Inspector F'),
        ]

        cursor.executemany('''
            INSERT INTO users (username, password_hash, role, full_name)
            VALUES (?, ?, ?, ?)
        ''', test_users)

    # Insert water supplies from the monthly report photo
    cursor.execute("SELECT COUNT(*) FROM water_supplies")
    if cursor.fetchone()[0] == 0:
        supplies = [
            # Treated Supplies
            ('Roaring River 1', 'treated', 'NWC', ''),
            ('Roaring River 2', 'treated', 'NWC', ''),
            ('Bluemede', 'treated', 'NWC', ''),
            ('Dantrout', 'treated', 'NWC', ''),
            ('Bluefield\'s', 'treated', 'NWC', ''),
            ('Negril/Logwood', 'treated', 'NWC', ''),
            ('Bethel Town/Cambridge', 'treated', 'NWC', ''),
            ('Venture-Williamsfield', 'treated', 'NWC', ''),
            ('Shettlewood', 'treated', 'NWC', ''),
            ('Cave', 'treated', 'NWC', ''),
            ('Carawina', 'treated', 'NWC', ''),
            ('Dean\'s Valley', 'treated', 'NWC', ''),
            ('New Works', 'treated', 'PC', ''),
            ('New Works-Steward Lands', 'treated', 'PC', ''),
            ('Castle Mountain', 'treated', 'PC', ''),
            ('Berkshire Shane', 'treated', 'PC Royal', ''),
            ('Army Mountains', 'treated', 'PC', ''),
            ('Beeston Spring', 'treated', 'PC', ''),
            ('Spring Gardens', 'treated', 'Private', ''),

            # Untreated Supplies
            ('Content', 'untreated', 'PC', ''),
            ('Holly Hill', 'untreated', 'PC', ''),
            ('Bunion (Bunyan)', 'untreated', 'PC', ''),
            ('Lundi', 'untreated', 'PC', ''),
            ('Pinnock Shafton', 'untreated', 'PC', ''),
            ('Orange Hill', 'untreated', 'PC', ''),
            ('Cairn Curran', 'untreated', 'PC', ''),
            ('Cedar Valley', 'untreated', 'PC', ''),
            ('Leamington', 'untreated', 'PC', ''),
            ('Charlie Mount', 'untreated', 'PC', ''),
            ('New Roads', 'untreated', 'PC', ''),
            ('Belvedere', 'untreated', 'PC', ''),
            ('York Mountain', 'untreated', 'PC', ''),
            ('Ashton', 'untreated', 'PC', ''),
            ('Kilmarnock', 'untreated', 'PC', ''),
            ('Bronti', 'untreated', 'PC', ''),
            ('Argyle Mountain', 'untreated', 'PC', ''),
            ('Bog', 'untreated', 'PC', ''),
            ('Porters Mountain', 'untreated', 'PC', ''),
            ('Ketto', 'untreated', 'Private', ''),
            ('Lambs River', 'untreated', 'PC', ''),
            ('Bath Mtns.', 'untreated', 'PC', '')
        ]
        cursor.executemany('''
            INSERT INTO water_supplies (name, type, agency, location)
            VALUES (?, ?, ?, ?)
        ''', supplies)

    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# Routes
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session['role'] == 'inspector':
        return render_template('index.html')
    elif session['role'] == 'admin':
        return render_template('admin.html')

@app.route('/inspector')
def inspector():
    if 'user_id' not in session or session['role'] != 'inspector':
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/admin')
def admin():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    return render_template('admin.html')

@app.route('/report')
def report():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('report.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        username = data['username']
        password = data['password']
        password_hash = hashlib.sha256(password.encode()).hexdigest()

        conn = get_db_connection()
        user = conn.execute('''
            SELECT * FROM users WHERE username = ? AND password_hash = ?
        ''', (username, password_hash)).fetchone()
        conn.close()

        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['full_name'] = user['full_name']
            return jsonify({'success': True, 'role': user['role']})
        else:
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

    return render_template_string('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Water Quality Monitoring - Login</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .login-container {
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 15px 35px rgba(0, 0, 0, 0.1);
            width: 100%;
            max-width: 400px;
        }
        .login-header {
            text-align: center;
            margin-bottom: 30px;
        }
        .login-header h1 {
            color: #333;
            font-size: 24px;
            margin-bottom: 10px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        .form-group label {
            display: block;
            margin-bottom: 5px;
            color: #333;
            font-weight: 600;
        }
        .form-group input {
            width: 100%;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-size: 16px;
        }
        .login-btn {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 5px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
        }
        .demo-creds {
            margin-top: 20px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 5px;
            font-size: 12px;
        }
        .alert {
            padding: 10px;
            margin-bottom: 15px;
            border-radius: 5px;
            color: #721c24;
            background: #f8d7da;
            display: none;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="login-header">
            <h1>Water Quality Monitoring</h1>
            <p>Please sign in to continue</p>
        </div>

        <div id="alert" class="alert"></div>

        <form id="loginForm">
            <div class="form-group">
                <label for="username">Username</label>
                <input type="text" id="username" name="username" required>
            </div>
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required>
            </div>
            <button type="submit" class="login-btn">Sign In</button>
        </form>

        <div class="demo-creds">
            <h4>Demo Credentials:</h4>
            <p><strong>Admin:</strong> admin / admin123</p>
            <p><strong>Inspector:</strong> inspector / inspector123</p>
        </div>
    </div>

    <script>
        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = {
                username: formData.get('username'),
                password: formData.get('password')
            };

            try {
                const response = await fetch('/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });

                const result = await response.json();
                if (result.success) {
                    if (result.role === 'inspector') {
                        window.location.href = '/inspector';
                    } else if (result.role === 'admin') {
                        window.location.href = '/admin';
                    }
                } else {
                    document.getElementById('alert').style.display = 'block';
                    document.getElementById('alert').textContent = result.message;
                }
            } catch (error) {
                document.getElementById('alert').style.display = 'block';
                document.getElementById('alert').textContent = 'Login failed';
            }
        });
    </script>
</body>
</html>
    ''')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# API Routes
@app.route('/api/supplies')
def get_supplies():
    conn = get_db_connection()
    supplies = conn.execute('SELECT * FROM water_supplies ORDER BY type, name').fetchall()
    conn.close()
    return jsonify([dict(supply) for supply in supplies])

@app.route('/api/monthly-data')
def get_monthly_data():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    now = datetime.now()
    month = now.month
    year = now.year

    conn = get_db_connection()

    # Get cumulative data from individual submissions for current month
    monthly_data = conn.execute('''
        SELECT
            ws.id as supply_id,
            ws.name as supply_name,
            ws.type,
            ws.agency,
            COALESCE(SUM(sub.visits), 0) as visits,
            COALESCE(SUM(sub.chlorine_total), 0) as chlorine_total,
            COALESCE(SUM(sub.chlorine_positive), 0) as chlorine_positive,
            COALESCE(SUM(sub.chlorine_negative), 0) as chlorine_negative,
            COALESCE(SUM(sub.bacteriological_positive), 0) as bacteriological_positive,
            COALESCE(SUM(sub.bacteriological_negative), 0) as bacteriological_negative,
            COALESCE(SUM(sub.bacteriological_pending), 0) as bacteriological_pending,
            MAX(sub.created_at) as last_updated
        FROM water_supplies ws
        LEFT JOIN inspection_submissions sub ON ws.id = sub.supply_id
            AND strftime('%m', sub.submission_date) = ?
            AND strftime('%Y', sub.submission_date) = ?
        GROUP BY ws.id, ws.name, ws.type, ws.agency
        ORDER BY ws.type, ws.agency, ws.name
    ''', (f"{month:02d}", str(year))).fetchall()
    conn.close()

    result = {}
    for data in monthly_data:
        result[data['supply_id']] = dict(data)

    return jsonify(result)

@app.route('/api/dashboard-data')
def get_dashboard_data():
    """Combined endpoint for admin dashboard - returns both supplies and monthly data"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    now = datetime.now()
    month = now.month
    year = now.year

    conn = get_db_connection()

    # Get all supplies
    supplies = conn.execute('SELECT * FROM water_supplies ORDER BY type, name').fetchall()

    # Get cumulative data from individual submissions for current month
    monthly_data = conn.execute('''
        SELECT
            ws.id as supply_id,
            ws.name as supply_name,
            ws.type,
            ws.agency,
            COALESCE(SUM(sub.visits), 0) as visits,
            COALESCE(SUM(sub.chlorine_total), 0) as chlorine_total,
            COALESCE(SUM(sub.chlorine_positive), 0) as chlorine_positive,
            COALESCE(SUM(sub.chlorine_negative), 0) as chlorine_negative,
            COALESCE(SUM(sub.bacteriological_positive), 0) as bacteriological_positive,
            COALESCE(SUM(sub.bacteriological_negative), 0) as bacteriological_negative,
            COALESCE(SUM(sub.bacteriological_pending), 0) as bacteriological_pending,
            MAX(sub.created_at) as last_updated
        FROM water_supplies ws
        LEFT JOIN inspection_submissions sub ON ws.id = sub.supply_id
            AND strftime('%m', sub.submission_date) = ?
            AND strftime('%Y', sub.submission_date) = ?
        GROUP BY ws.id, ws.name, ws.type, ws.agency
        ORDER BY ws.type, ws.agency, ws.name
    ''', (f"{month:02d}", str(year))).fetchall()

    conn.close()

    # Format monthly data as dict indexed by supply_id
    monthly_data_dict = {}
    for data in monthly_data:
        monthly_data_dict[data['supply_id']] = dict(data)

    return jsonify({
        'supplies': [dict(supply) for supply in supplies],
        'monthly_data': monthly_data_dict
    })

@app.route('/api/submit-inspection', methods=['POST'])
def submit_inspection():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Insert new inspection submission
        cursor.execute('''
            INSERT INTO inspection_submissions
            (supply_id, inspector_id, submission_date, visits, chlorine_total, chlorine_positive,
             chlorine_negative, bacteriological_positive, bacteriological_negative,
             bacteriological_pending, remarks)
            VALUES (?, ?, date('now'), ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['supply_id'], session['user_id'], data.get('visits', 0),
            data.get('chlorine_total', 0), data.get('chlorine_positive', 0),
            data.get('chlorine_negative', 0), data.get('bacteriological_positive', 0),
            data.get('bacteriological_negative', 0), data.get('bacteriological_pending', 0),
            data.get('remarks', '')
        ))

        submission_id = cursor.lastrowid

        # Get the submission with supply info
        submission_data = cursor.execute('''
            SELECT s.*, ws.name as supply_name, ws.type, ws.agency,
                   u.full_name as inspector_name
            FROM inspection_submissions s
            JOIN water_supplies ws ON s.supply_id = ws.id
            JOIN users u ON s.inspector_id = u.id
            WHERE s.id = ?
        ''', (submission_id,)).fetchone()

        conn.commit()
        conn.close()

        # Emit real-time update to admin
        socketio.emit('new_submission', dict(submission_data), room='admin')

        return jsonify({'success': True, 'submission': dict(submission_data)})

    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/my-submissions')
def get_my_submissions():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    conn = get_db_connection()
    submissions = conn.execute('''
        SELECT s.*, ws.name as supply_name, ws.type, ws.agency
        FROM inspection_submissions s
        JOIN water_supplies ws ON s.supply_id = ws.id
        WHERE s.inspector_id = ?
        ORDER BY s.created_at DESC
        LIMIT 10
    ''', (session['user_id'],)).fetchall()
    conn.close()

    return jsonify([dict(submission) for submission in submissions])

@app.route('/api/update-supply-data', methods=['POST'])
def update_supply_data():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.json
    now = datetime.now()
    month = now.month
    year = now.year

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT OR REPLACE INTO monthly_supply_data
            (supply_id, month, year, visits, chlorine_total, chlorine_positive,
             chlorine_negative, bacteriological_positive, bacteriological_negative,
             bacteriological_pending, remarks, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (
            data['supply_id'], month, year, data['visits'],
            data['chlorine_total'], data['chlorine_positive'], data['chlorine_negative'],
            data['bacteriological_positive'], data['bacteriological_negative'],
            data['bacteriological_pending'], data.get('remarks', '')
        ))

        conn.commit()

        # Get updated data with supply info
        updated_data = cursor.execute('''
            SELECT msd.*, s.name as supply_name, s.agency, s.type
            FROM monthly_supply_data msd
            JOIN water_supplies s ON msd.supply_id = s.id
            WHERE msd.supply_id = ? AND msd.month = ? AND msd.year = ?
        ''', (data['supply_id'], month, year)).fetchone()

        conn.close()

        # Emit real-time update
        socketio.emit('supply_updated', dict(updated_data), room='admin')

        return jsonify({'success': True, 'data': dict(updated_data)})

    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/report/<int:year>/<int:month>')
def get_monthly_report(year, month):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    conn = get_db_connection()

    # Get all supplies
    supplies = conn.execute('SELECT * FROM water_supplies ORDER BY type, agency, name').fetchall()

    # Get cumulative data from individual submissions for the specified month/year
    monthly_data = conn.execute('''
        SELECT
            ws.id as supply_id,
            ws.name as supply_name,
            ws.type,
            ws.agency,
            COALESCE(SUM(sub.visits), 0) as visits,
            COALESCE(SUM(sub.chlorine_total), 0) as chlorine_total,
            COALESCE(SUM(sub.chlorine_positive), 0) as chlorine_positive,
            COALESCE(SUM(sub.chlorine_negative), 0) as chlorine_negative,
            COALESCE(SUM(sub.bacteriological_positive), 0) as bacteriological_positive,
            COALESCE(SUM(sub.bacteriological_negative), 0) as bacteriological_negative,
            COALESCE(SUM(sub.bacteriological_pending), 0) as bacteriological_pending,
            GROUP_CONCAT(sub.remarks, '; ') as remarks,
            MAX(sub.created_at) as last_updated
        FROM water_supplies ws
        LEFT JOIN inspection_submissions sub ON ws.id = sub.supply_id
            AND strftime('%m', sub.submission_date) = ?
            AND strftime('%Y', sub.submission_date) = ?
        GROUP BY ws.id, ws.name, ws.type, ws.agency
        ORDER BY ws.type, ws.agency, ws.name
    ''', (f"{month:02d}", str(year))).fetchall()

    conn.close()

    return jsonify({
        'supplies': [dict(supply) for supply in supplies],
        'monthly_data': [dict(data) for data in monthly_data]
    })

# WebSocket Events
@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)
    print(f"User joined room: {room}")

@socketio.on('leave')
def on_leave(data):
    room = data['room']
    leave_room(room)
    print(f"User left room: {room}")

# Initialize database on module import (for production)
init_db()

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5004))
    debug = os.environ.get('FLASK_ENV', 'development') == 'development'

    if debug:
        # Development mode
        socketio.run(app, host='0.0.0.0', port=port, debug=True, allow_unsafe_werkzeug=True)
    else:
        # Production mode - but allow unsafe werkzeug for local testing and Render deployment
        socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)