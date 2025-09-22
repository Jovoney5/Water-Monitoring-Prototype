from flask import Flask, request, jsonify, session, redirect, url_for, render_template_string, render_template
from flask_socketio import SocketIO, emit, join_room, leave_room
import sqlite3
import hashlib
from datetime import datetime, date, timedelta
import json
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'water-monitoring-secret-key-2024'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)  # Sessions last 7 days
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
            parish TEXT NOT NULL DEFAULT 'Westmoreland',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Add parish column to existing users table if it doesn't exist
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN parish TEXT DEFAULT "Westmoreland"')
    except sqlite3.OperationalError:
        # Column already exists
        pass

    # Update existing users without parish to have Westmoreland
    cursor.execute('UPDATE users SET parish = "Westmoreland" WHERE parish IS NULL OR parish = ""')

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
            sampling_point_id INTEGER,
            submission_date DATE NOT NULL,
            visits INTEGER DEFAULT 0,
            chlorine_total INTEGER DEFAULT 0,
            chlorine_positive INTEGER DEFAULT 0,
            chlorine_negative INTEGER DEFAULT 0,
            chlorine_positive_range TEXT,
            chlorine_negative_range TEXT,
            bacteriological_positive INTEGER DEFAULT 0,
            bacteriological_negative INTEGER DEFAULT 0,
            bacteriological_pending INTEGER DEFAULT 0,
            isolated_organism TEXT,
            remarks TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (supply_id) REFERENCES water_supplies (id),
            FOREIGN KEY (inspector_id) REFERENCES users (id),
            FOREIGN KEY (sampling_point_id) REFERENCES sampling_points (id)
        )
    ''')

    # Sampling points table for water supplies
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sampling_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supply_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            location TEXT,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (supply_id) REFERENCES water_supplies (id)
        )
    ''')

    # Tasks table for inspector assignments
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inspector_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            assigned_to_id INTEGER NOT NULL,
            supply_id INTEGER,
            priority TEXT NOT NULL CHECK (priority IN ('Low', 'Medium', 'High', 'Urgent')),
            due_date DATE NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending', 'accepted', 'in_progress', 'completed', 'rejected')) DEFAULT 'pending',
            created_by_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (assigned_to_id) REFERENCES users (id),
            FOREIGN KEY (supply_id) REFERENCES water_supplies (id),
            FOREIGN KEY (created_by_id) REFERENCES users (id)
        )
    ''')

    # Insert default users
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        # Test users for demo/testing phase
        test_users = [
            # Admins (password: admin123)
            ('admin', hashlib.sha256('admin123'.encode()).hexdigest(), 'admin', 'System Administrator', 'Westmoreland'),
            ('admin2', hashlib.sha256('admin123'.encode()).hexdigest(), 'admin', 'Senior Administrator', 'Westmoreland'),

            # Inspectors (password: inspector123)
            ('inspector', hashlib.sha256('inspector123'.encode()).hexdigest(), 'inspector', 'Water Quality Inspector', 'Westmoreland'),
            ('inspector1', hashlib.sha256('inspector123'.encode()).hexdigest(), 'inspector', 'Field Inspector A', 'Westmoreland'),
            ('inspector2', hashlib.sha256('inspector123'.encode()).hexdigest(), 'inspector', 'Field Inspector B', 'Westmoreland'),
            ('inspector3', hashlib.sha256('inspector123'.encode()).hexdigest(), 'inspector', 'Field Inspector C', 'Westmoreland'),
            ('inspector4', hashlib.sha256('inspector123'.encode()).hexdigest(), 'inspector', 'Field Inspector D', 'Westmoreland'),
            ('inspector5', hashlib.sha256('inspector123'.encode()).hexdigest(), 'inspector', 'Field Inspector E', 'Westmoreland'),
            ('inspector6', hashlib.sha256('inspector123'.encode()).hexdigest(), 'inspector', 'Field Inspector F', 'Westmoreland'),

            # Trelawny Inspectors (password: inspector123)
            ('trelawny1', hashlib.sha256('inspector123'.encode()).hexdigest(), 'inspector', 'Trelawny Inspector A', 'Trelawny'),
            ('trelawny2', hashlib.sha256('inspector123'.encode()).hexdigest(), 'inspector', 'Trelawny Inspector B', 'Trelawny'),
            ('trelawny3', hashlib.sha256('inspector123'.encode()).hexdigest(), 'inspector', 'Trelawny Inspector C', 'Trelawny'),

            # Trelawny Admin (password: admin123)
            ('trelawny_admin', hashlib.sha256('admin123'.encode()).hexdigest(), 'admin', 'Trelawny Administrator', 'Trelawny'),
        ]

        cursor.executemany('''
            INSERT INTO users (username, password_hash, role, full_name, parish)
            VALUES (?, ?, ?, ?, ?)
        ''', test_users)

    # Insert water supplies from the updated list
    cursor.execute('SELECT COUNT(*) FROM water_supplies')
    if cursor.fetchone()[0] == 0:
        supplies = [
            # Treated Supplies
            ('Roaring River 1', 'treated', 'NWC', ''),
            ('Roaring River 2', 'treated', 'NWC', ''),
            ('Bulstrode', 'treated', 'NWC', ''),
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
            ('Berkshire', 'treated', 'PC', ''),
            ('Amity Mountains', 'treated', 'PC', ''),
            ('Beeston Spring', 'treated', 'PC', ''),
            ('Spring Gardens', 'treated', 'Private', ''),

            # Untreated Supplies
            ('Content', 'untreated', 'PC', ''),
            ('Holly Hill', 'untreated', 'PC', ''),
            ('Bunion (Bunyan)', 'untreated', 'PC', ''),
            ('Lundi', 'untreated', 'PC', ''),
            ('Pinnock Shafton', 'untreated', 'PC', ''),
            ('Orange Hill', 'untreated', 'PC', ''),
            ('Cair Curran Cedar Valley', 'untreated', 'PC', ''),
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

    # Insert sampling points for Roaring River supplies
    cursor.execute('SELECT COUNT(*) FROM sampling_points')
    if cursor.fetchone()[0] == 0:
        # Get the IDs for Roaring River 1 and Roaring River 2
        roaring_river_1_id = cursor.execute('SELECT id FROM water_supplies WHERE name = "Roaring River 1"').fetchone()[0]
        roaring_river_2_id = cursor.execute('SELECT id FROM water_supplies WHERE name = "Roaring River 2"').fetchone()[0]

        # Clear existing sampling points first (if updating)
        cursor.execute('DELETE FROM sampling_points WHERE supply_id IN (SELECT id FROM water_supplies WHERE name IN ("Roaring River 1", "Roaring River 2"))')

        sampling_points = [
            # Roaring River 1 sampling points
            (roaring_river_1_id, 'tap@ Health Department (old plant)', 'roaring river', 'Health Department tap from old plant'),
            (roaring_river_1_id, 'tap@ Hospital Storage tank (old plant)', 'roaring river', 'Hospital storage tank from old plant'),
            (roaring_river_1_id, 'standpipe@135 Dalling Street (old plant)', 'roaring river', 'Standpipe at 135 Dalling Street from old plant'),
            (roaring_river_1_id, 'tap@ loading Bay, Petersfield (old plant)', 'roaring river', 'Loading Bay tap at Petersfield from old plant'),
            (roaring_river_1_id, 'standpipe @ Lower Darliston (new plant)', 'roaring river', 'Standpipe at Lower Darliston from new plant'),
            (roaring_river_1_id, 'standpipe@ Carawina Road (old plant)', 'roaring river', 'Standpipe at Carawina Road from old plant'),
            (roaring_river_1_id, 'standpipe@ Roaring River District (old plant)', 'roaring river', 'Standpipe at Roaring River District from old plant'),
            (roaring_river_1_id, 'tap@ shop, Michael Smith Ave (new plant)', 'roaring river', 'Shop tap at Michael Smith Ave from new plant'),
            (roaring_river_1_id, 'tap@Dud\'s Bar, Whithorn (new plant)', 'roaring river', 'Dud\'s Bar tap at Whithorn from new plant'),
            (roaring_river_1_id, 'standpipe@ Barneyside All age', 'roaring river', 'Standpipe at Barneyside All age'),

            # Roaring River 2 sampling points (same locations)
            (roaring_river_2_id, 'tap@ Health Department (old plant)', 'roaring river', 'Health Department tap from old plant'),
            (roaring_river_2_id, 'tap@ Hospital Storage tank (old plant)', 'roaring river', 'Hospital storage tank from old plant'),
            (roaring_river_2_id, 'standpipe@135 Dalling Street (old plant)', 'roaring river', 'Standpipe at 135 Dalling Street from old plant'),
            (roaring_river_2_id, 'tap@ loading Bay, Petersfield (old plant)', 'roaring river', 'Loading Bay tap at Petersfield from old plant'),
            (roaring_river_2_id, 'standpipe @ Lower Darliston (new plant)', 'roaring river', 'Standpipe at Lower Darliston from new plant'),
            (roaring_river_2_id, 'standpipe@ Carawina Road (old plant)', 'roaring river', 'Standpipe at Carawina Road from old plant'),
            (roaring_river_2_id, 'standpipe@ Roaring River District (old plant)', 'roaring river', 'Standpipe at Roaring River District from old plant'),
            (roaring_river_2_id, 'tap@ shop, Michael Smith Ave (new plant)', 'roaring river', 'Shop tap at Michael Smith Ave from new plant'),
            (roaring_river_2_id, 'tap@Dud\'s Bar, Whithorn (new plant)', 'roaring river', 'Dud\'s Bar tap at Whithorn from new plant'),
            (roaring_river_2_id, 'standpipe@ Barneyside All age', 'roaring river', 'Standpipe at Barneyside All age'),
        ]

        cursor.executemany('''
            INSERT INTO sampling_points (supply_id, name, location, description)
            VALUES (?, ?, ?, ?)
        ''', sampling_points)

    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def add_sample_data():
    '''Add sample inspection data for testing charts'''
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if sample data already exists
    existing_data = cursor.execute('SELECT COUNT(*) FROM inspection_submissions').fetchone()[0]
    if existing_data > 50:  # Keep existing data, only add if very little exists
        conn.close()
        return

    # Get supply IDs and inspector IDs
    supplies = cursor.execute('SELECT id FROM water_supplies LIMIT 10').fetchall()
    inspectors = cursor.execute('SELECT id FROM users WHERE role = "inspector" LIMIT 3').fetchall()

    if not supplies or not inspectors:
        conn.close()
        return

    # Create sample data for the last 30 days
    import random

    sample_data = []
    for i in range(30):  # 30 days of data
        date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')

        # Create 2-5 random submissions per day
        for j in range(random.randint(2, 5)):
            supply_id = random.choice(supplies)['id']
            inspector_id = random.choice(inspectors)['id']

            sample_data.append((
                supply_id,
                inspector_id,
                None,  # sampling_point_id
                date,
                random.randint(1, 3),  # visits
                random.randint(5, 15),  # chlorine_total
                random.randint(3, 12),  # chlorine_positive
                random.randint(1, 5),   # chlorine_negative
                '',  # chlorine_positive_range
                '',  # chlorine_negative_range
                random.randint(0, 3),   # bacteriological_positive
                random.randint(2, 8),   # bacteriological_negative
                random.randint(0, 2),   # bacteriological_pending
                '',  # isolated_organism
                'Sample inspection data'  # remarks
            ))

    cursor.executemany('''
        INSERT INTO inspection_submissions
        (supply_id, inspector_id, sampling_point_id, submission_date, visits,
         chlorine_total, chlorine_positive, chlorine_negative, chlorine_positive_range,
         chlorine_negative_range, bacteriological_positive, bacteriological_negative,
         bacteriological_pending, isolated_organism, remarks)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', sample_data)

    conn.commit()
    conn.close()
    print('Sample data added for chart testing')

# Routes
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Redirect users to their parish-specific dashboard
    user_parish = session.get('parish', 'Westmoreland')

    if user_parish == 'Trelawny':
        return redirect(url_for('trelawny'))
    elif user_parish == 'Westmoreland':
        if session['role'] == 'inspector':
            return render_template('index.html')
        elif session['role'] == 'admin':
            return render_template('admin.html')
    else:
        # Fallback for unsupported parishes
        return redirect(url_for('login'))

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

@app.route('/trelawny')
def trelawny():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Only allow Trelawny users to access this dashboard
    user_parish = session.get('parish', 'Westmoreland')
    if user_parish != 'Trelawny':
        return redirect(url_for('index'))

    return render_template('trelawny.html')

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
            # Get parish, default to Westmoreland for existing users or if parish is None
            user_parish = user['parish'] if user['parish'] else 'Westmoreland'

            # Update user's parish to Westmoreland if it's None (for existing users)
            if not user['parish']:
                conn = get_db_connection()
                conn.execute('UPDATE users SET parish = ? WHERE id = ?', ('Westmoreland', user['id']))
                conn.commit()
                conn.close()

            # Allow users from supported parishes
            supported_parishes = ['Westmoreland', 'Trelawny']
            if user_parish not in supported_parishes:
                return jsonify({
                    'success': False,
                    'message': f'Access denied. {user_parish} dashboard not yet available. Supported parishes: {", ".join(supported_parishes)}.'
                }), 403

            session.permanent = True  # Make session persistent
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['full_name'] = user['full_name']
            session['parish'] = user_parish
            return jsonify({'success': True, 'role': user['role'], 'parish': session['parish']})
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
            min-height: 100vh;
            display: flex;
            align-items: flex-end;
            justify-content: flex-end;
            overflow: hidden;
            position: relative;
            padding: 20px;
        }

        .video-background {
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 100vh;
            height: 100vh;
            object-fit: cover;
            object-position: center;
            z-index: 0;
            border-radius: 15px;
            box-shadow:
                0 8px 32px rgba(0, 0, 0, 0.3),
                0 4px 16px rgba(0, 0, 0, 0.2),
                inset 0 0 0 1px rgba(255, 255, 255, 0.1),
                0 0 0 1px rgba(255, 255, 255, 0.05);
        }

        /* Video container with water reflection effect */
        .video-container {
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 100vh;
            height: 100vh;
            z-index: 0;
            border-radius: 15px;
        }

        .video-container::before {
            content: '';
            position: absolute;
            top: -10px;
            left: -10px;
            right: -10px;
            bottom: -10px;
            background: radial-gradient(ellipse at center, rgba(173, 216, 230, 0.3) 0%, transparent 70%);
            border-radius: 25px;
            z-index: -1;
        }

        .video-container::after {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: linear-gradient(135deg,
                rgba(255, 255, 255, 0.1) 0%,
                transparent 20%,
                transparent 80%,
                rgba(0, 0, 0, 0.1) 100%);
            border-radius: 15px;
            pointer-events: none;
            z-index: 1;
        }


        .login-container {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.3);
            width: 100%;
            max-width: 350px;
            border: 1px solid rgba(255, 255, 255, 0.2);
            z-index: 1;
            position: relative;
        }

        .login-header {
            text-align: center;
            margin-bottom: 20px;
        }

        .login-header h1 {
            color: #333;
            font-size: 22px;
            margin-bottom: 8px;
            text-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        .login-header p {
            color: #666;
            font-size: 14px;
        }

        .form-group {
            margin-bottom: 15px;
        }

        .form-group label {
            display: block;
            margin-bottom: 8px;
            color: #333;
            font-weight: 600;
            font-size: 14px;
        }

        .form-group input {
            width: 100%;
            padding: 14px;
            border: 2px solid rgba(102, 126, 234, 0.2);
            border-radius: 8px;
            font-size: 16px;
            background: rgba(255, 255, 255, 0.9);
            transition: all 0.3s ease;
        }

        .form-group input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 15px rgba(102, 126, 234, 0.2);
            background: white;
        }

        .login-btn {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
        }

        .login-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
        }

        .login-btn:active {
            transform: translateY(0);
        }

        .demo-creds {
            margin-top: 15px;
            padding: 15px;
            background: rgba(248, 249, 250, 0.9);
            backdrop-filter: blur(5px);
            border-radius: 8px;
            font-size: 12px;
            border: 1px solid rgba(0,0,0,0.1);
        }

        .demo-creds h4 {
            color: #333;
            margin-bottom: 8px;
            font-size: 13px;
        }

        .demo-creds p {
            margin: 5px 0;
            color: #555;
        }

        .alert {
            padding: 12px;
            margin-bottom: 20px;
            border-radius: 8px;
            color: #721c24;
            background: rgba(248, 215, 218, 0.95);
            border: 1px solid rgba(245, 198, 203, 0.8);
            backdrop-filter: blur(5px);
            display: none;
        }

        /* Water-themed background */
        .video-fallback {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: linear-gradient(180deg, #87ceeb 0%, #4682b4 50%, #1e6091 100%);
            z-index: -2;
        }

        /* Water bubbles animation container */
        .water-effects {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: -1;
            pointer-events: none;
            overflow: hidden;
        }

        .water-bubble {
            position: absolute;
            border-radius: 50%;
            background: radial-gradient(circle at 30% 30%, rgba(255, 255, 255, 0.8), rgba(173, 216, 230, 0.6), rgba(135, 206, 250, 0.3));
            box-shadow: inset 0 0 10px rgba(255, 255, 255, 0.5), 0 0 20px rgba(173, 216, 230, 0.3);
            animation: bubbleFloat 8s linear infinite;
        }

        /* Different bubble sizes and positions */
        .water-bubble:nth-child(1) { width: 15px; height: 15px; left: 5%; animation-delay: 0s; animation-duration: 6s; }
        .water-bubble:nth-child(2) { width: 25px; height: 25px; left: 15%; animation-delay: -1s; animation-duration: 8s; }
        .water-bubble:nth-child(3) { width: 12px; height: 12px; left: 25%; animation-delay: -2s; animation-duration: 7s; }
        .water-bubble:nth-child(4) { width: 30px; height: 30px; left: 35%; animation-delay: -3s; animation-duration: 9s; }
        .water-bubble:nth-child(5) { width: 8px; height: 8px; left: 45%; animation-delay: -4s; animation-duration: 5s; }
        .water-bubble:nth-child(6) { width: 20px; height: 20px; left: 55%; animation-delay: -1.5s; animation-duration: 7.5s; }
        .water-bubble:nth-child(7) { width: 18px; height: 18px; left: 65%; animation-delay: -2.5s; animation-duration: 6.5s; }
        .water-bubble:nth-child(8) { width: 22px; height: 22px; left: 75%; animation-delay: -0.5s; animation-duration: 8.5s; }
        .water-bubble:nth-child(9) { width: 14px; height: 14px; left: 85%; animation-delay: -3.5s; animation-duration: 7s; }
        .water-bubble:nth-child(10) { width: 28px; height: 28px; left: 95%; animation-delay: -1.2s; animation-duration: 9s; }

        /* Right side bubbles */
        .water-bubble:nth-child(11) { width: 16px; height: 16px; right: 5%; animation-delay: -0.8s; animation-duration: 6.8s; }
        .water-bubble:nth-child(12) { width: 24px; height: 24px; right: 15%; animation-delay: -2.2s; animation-duration: 8.2s; }
        .water-bubble:nth-child(13) { width: 11px; height: 11px; right: 25%; animation-delay: -3.8s; animation-duration: 5.8s; }
        .water-bubble:nth-child(14) { width: 26px; height: 26px; right: 35%; animation-delay: -1.8s; animation-duration: 7.8s; }
        .water-bubble:nth-child(15) { width: 19px; height: 19px; right: 45%; animation-delay: -2.8s; animation-duration: 6.8s; }

        /* Additional scattered bubbles */
        .water-bubble:nth-child(16) { width: 13px; height: 13px; left: 10%; animation-delay: -4.5s; animation-duration: 6.2s; }
        .water-bubble:nth-child(17) { width: 21px; height: 21px; left: 30%; animation-delay: -1.7s; animation-duration: 8.7s; }
        .water-bubble:nth-child(18) { width: 17px; height: 17px; left: 50%; animation-delay: -3.2s; animation-duration: 7.2s; }
        .water-bubble:nth-child(19) { width: 23px; height: 23px; left: 70%; animation-delay: -0.7s; animation-duration: 5.7s; }
        .water-bubble:nth-child(20) { width: 15px; height: 15px; left: 90%; animation-delay: -2.7s; animation-duration: 6.7s; }

        /* Water ripple effects */
        .water-ripple {
            position: absolute;
            border: 2px solid rgba(173, 216, 230, 0.4);
            border-radius: 50%;
            animation: ripple 4s ease-out infinite;
        }

        .water-ripple:nth-child(21) {
            width: 50px;
            height: 50px;
            top: 20%;
            left: 20%;
            animation-delay: 0s;
        }

        .water-ripple:nth-child(22) {
            width: 80px;
            height: 80px;
            top: 60%;
            right: 25%;
            animation-delay: -2s;
        }

        .water-ripple:nth-child(23) {
            width: 60px;
            height: 60px;
            bottom: 30%;
            left: 80%;
            animation-delay: -1s;
        }

        @keyframes bubbleFloat {
            0% {
                transform: translateY(100vh) translateX(0px) scale(0);
                opacity: 0;
            }
            10% {
                opacity: 1;
                transform: translateY(90vh) translateX(0px) scale(1);
            }
            50% {
                transform: translateY(50vh) translateX(20px) scale(1.1);
                opacity: 0.8;
            }
            100% {
                transform: translateY(-10vh) translateX(-10px) scale(0.8);
                opacity: 0;
            }
        }

        @keyframes ripple {
            0% {
                transform: scale(0);
                opacity: 1;
            }
            50% {
                opacity: 0.5;
            }
            100% {
                transform: scale(4);
                opacity: 0;
            }
        }


        /* Mobile responsive */
        @media (max-width: 480px) {
            body {
                align-items: center;
                justify-content: center;
                padding: 15px;
            }

            .login-container {
                max-width: 100%;
                padding: 20px;
            }

            .login-header h1 {
                font-size: 20px;
            }
        }
    </style>
</head>
<body>
    <!-- Fallback background -->
    <div class="video-fallback"></div>

    <!-- Water effects with bubbles and ripples -->
    <div class="water-effects">
        <!-- Water bubbles -->
        <div class="water-bubble"></div>
        <div class="water-bubble"></div>
        <div class="water-bubble"></div>
        <div class="water-bubble"></div>
        <div class="water-bubble"></div>
        <div class="water-bubble"></div>
        <div class="water-bubble"></div>
        <div class="water-bubble"></div>
        <div class="water-bubble"></div>
        <div class="water-bubble"></div>
        <div class="water-bubble"></div>
        <div class="water-bubble"></div>
        <div class="water-bubble"></div>
        <div class="water-bubble"></div>
        <div class="water-bubble"></div>
        <div class="water-bubble"></div>
        <div class="water-bubble"></div>
        <div class="water-bubble"></div>
        <div class="water-bubble"></div>
        <div class="water-bubble"></div>
        <!-- Water ripples -->
        <div class="water-ripple"></div>
        <div class="water-ripple"></div>
        <div class="water-ripple"></div>
    </div>

    <!-- Video background with tile effect -->
    <div class="video-container">
        <video class="video-background" autoplay muted loop playsinline>
            <source src="{{ url_for('static', filename='videos/water.mp4') }}" type="video/mp4">
            <!-- Fallback for browsers that don't support video -->
            Your browser does not support the video tag.
        </video>
    </div>



    <div class="login-container">
        <div class="login-header">
            <h1>💧 Water Quality Monitoring</h1>
            <p>Please sign in to continue</p>
        </div>

        <div id="alert" class="alert"></div>

        <form id="loginForm">
            <div class="form-group">
                <label for="username">Username</label>
                <input type="text" id="username" name="username" required autocomplete="username">
            </div>
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required autocomplete="current-password">
            </div>
            <button type="submit" class="login-btn">Sign In</button>
        </form>

        <div class="demo-creds">
            <h4>🔑 Demo Credentials:</h4>
            <p><strong>Admin:</strong> admin / admin123</p>
            <p><strong>Inspector:</strong> inspector / inspector123</p>
        </div>
    </div>

    <script>
        // Handle video loading errors
        const video = document.querySelector('.video-background');

        video.addEventListener('error', function() {
            console.log('Video failed to load, using fallback background');
            video.style.display = 'none';
        });


        // Ensure video plays on mobile devices
        video.addEventListener('loadeddata', function() {
            video.play().catch(function(error) {
                console.log('Video autoplay failed:', error);
                // Video will still show as a static frame
            });
        });



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

@app.route('/api/sampling-points/<int:supply_id>')
def get_sampling_points(supply_id):
    conn = get_db_connection()
    sampling_points = conn.execute('''
        SELECT sp.*, ws.name as supply_name
        FROM sampling_points sp
        JOIN water_supplies ws ON sp.supply_id = ws.id
        WHERE sp.supply_id = ?
        ORDER BY sp.name
    ''', (supply_id,)).fetchall()
    conn.close()
    return jsonify([dict(point) for point in sampling_points])

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

@app.route('/api/chart-data')
def get_chart_data():
    """Chart data endpoint for analytics visualization"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    chart_type = request.args.get('type', 'chlorine')
    time_range = request.args.get('range', '3months')
    supply_filter = request.args.get('supply', 'all')

    conn = get_db_connection()

    try:
        # Calculate date range
        now = datetime.now()
        if time_range == '3months':
            start_date = now - timedelta(days=90)
        elif time_range == '6months':
            start_date = now - timedelta(days=180)
        elif time_range == 'year':
            start_date = now - timedelta(days=365)
        else:
            start_date = now - timedelta(days=730)  # 2 years for 'all'

        # Build supply filter condition
        supply_condition = ""
        params = [start_date.strftime('%Y-%m-%d')]
        if supply_filter != 'all':
            supply_condition = " AND s.supply_id = ?"
            params.append(supply_filter)

        # Get time series data based on chart type
        time_series_data = []

        if chart_type == 'chlorine':
            # Get chlorine data over time
            query = f'''
                SELECT
                    DATE(s.submission_date) as date,
                    AVG(s.chlorine_total) as avg_chlorine,
                    ws.name as supply_name
                FROM inspection_submissions s
                JOIN water_supplies ws ON s.supply_id = ws.id
                WHERE s.submission_date >= ?{supply_condition}
                GROUP BY DATE(s.submission_date), s.supply_id
                ORDER BY s.submission_date
            '''

        elif chart_type == 'bacteriological':
            # Get bacteriological test data over time
            query = f'''
                SELECT
                    DATE(s.submission_date) as date,
                    SUM(s.bacteriological_positive + s.bacteriological_negative + s.bacteriological_pending) as total_tests,
                    ws.name as supply_name
                FROM inspection_submissions s
                JOIN water_supplies ws ON s.supply_id = ws.id
                WHERE s.submission_date >= ?{supply_condition}
                GROUP BY DATE(s.submission_date), s.supply_id
                ORDER BY s.submission_date
            '''

        elif chart_type == 'visits':
            # Get visits data over time
            query = f'''
                SELECT
                    DATE(s.submission_date) as date,
                    SUM(s.visits) as total_visits,
                    ws.name as supply_name
                FROM inspection_submissions s
                JOIN water_supplies ws ON s.supply_id = ws.id
                WHERE s.submission_date >= ?{supply_condition}
                GROUP BY DATE(s.submission_date), s.supply_id
                ORDER BY s.submission_date
            '''

        elif chart_type == 'distribution':
            # For distribution charts, we'll use the supply count over time
            query = f'''
                SELECT
                    DATE(s.submission_date) as date,
                    COUNT(DISTINCT s.supply_id) as supply_count,
                    ws.name as supply_name
                FROM inspection_submissions s
                JOIN water_supplies ws ON s.supply_id = ws.id
                WHERE s.submission_date >= ?{supply_condition}
                GROUP BY DATE(s.submission_date)
                ORDER BY s.submission_date
            '''

        else:
            # Default case - just return empty data
            query = '''SELECT DATE('now') as date, 0 as value, 'Default' as supply_name'''

        results = conn.execute(query, params).fetchall()

        # Convert to TradingView format
        for row in results:
            timestamp = int(datetime.strptime(row['date'], '%Y-%m-%d').timestamp())
            if chart_type == 'chlorine':
                value = float(row['avg_chlorine'] or 0)
            elif chart_type == 'bacteriological':
                value = float(row['total_tests'] or 0)
            elif chart_type == 'visits':
                value = float(row['total_visits'] or 0)
            elif chart_type == 'distribution':
                value = float(row['supply_count'] or 0)
            else:
                value = 0

            time_series_data.append({
                'time': timestamp,
                'value': value
            })

        # Get distribution data for pie chart
        distribution_data = {}

        if chart_type == 'chlorine':
            # Distribution of chlorine levels by range
            ranges = conn.execute(f'''
                SELECT
                    CASE
                        WHEN s.chlorine_total < 0.5 THEN 'Low (< 0.5 mg/L)'
                        WHEN s.chlorine_total < 1.0 THEN 'Normal (0.5-1.0 mg/L)'
                        ELSE 'High (> 1.0 mg/L)'
                    END as range_category,
                    COUNT(*) as count
                FROM inspection_submissions s
                WHERE s.submission_date >= ?{supply_condition}
                GROUP BY range_category
            ''', params).fetchall()

            distribution_data = {
                'labels': [row['range_category'] for row in ranges],
                'values': [row['count'] for row in ranges],
                'title': 'Chlorine Level Distribution'
            }

        elif chart_type == 'bacteriological':
            # Distribution of test results
            results_dist = conn.execute(f'''
                SELECT
                    SUM(s.bacteriological_positive) as positive,
                    SUM(s.bacteriological_negative) as negative,
                    SUM(s.bacteriological_pending) as pending
                FROM inspection_submissions s
                WHERE s.submission_date >= ?{supply_condition}
            ''', params).fetchone()

            distribution_data = {
                'labels': ['Positive', 'Negative', 'Pending'],
                'values': [results_dist['positive'] or 0, results_dist['negative'] or 0, results_dist['pending'] or 0],
                'title': 'Bacteriological Test Results'
            }

        else:
            # Supply type distribution
            ws_supply_condition = ""
            if supply_filter != 'all':
                ws_supply_condition = " AND ws.id = ?"

            supply_types = conn.execute(f'''
                SELECT ws.type, COUNT(DISTINCT ws.id) as count
                FROM water_supplies ws
                WHERE EXISTS (
                    SELECT 1 FROM inspection_submissions s
                    WHERE s.supply_id = ws.id AND s.submission_date >= ?
                    {ws_supply_condition}
                )
                GROUP BY ws.type
            ''', params).fetchall()

            distribution_data = {
                'labels': [row['type'].title() + ' Water' for row in supply_types],
                'values': [row['count'] for row in supply_types],
                'title': 'Water Supply Types'
            }

        conn.close()

        return jsonify({
            'timeSeries': time_series_data,
            'distribution': distribution_data
        })

    except Exception as e:
        conn.close()
        print(f"Chart data error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/parish-comparison')
def get_parish_comparison():
    """Parish comparison data endpoint for multi-parish analytics"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    time_range = request.args.get('range', '3months')
    chart_type = request.args.get('type', 'chlorine')

    conn = get_db_connection()

    try:
        # Calculate date range
        now = datetime.now()
        if time_range == '3months':
            start_date = now - timedelta(days=90)
        elif time_range == '6months':
            start_date = now - timedelta(days=180)
        elif time_range == 'year':
            start_date = now - timedelta(days=365)
        else:
            start_date = now - timedelta(days=730)  # 2 years for 'all'

        parish_data = {}
        parishes = ['Westmoreland', 'Trelawny', 'Hanover', 'St. James']  # Add more as needed

        for parish in parishes:
            if chart_type == 'chlorine':
                # Get chlorine data for this parish
                query = '''
                    SELECT
                        DATE(s.submission_date) as date,
                        AVG(s.chlorine_total) as avg_chlorine,
                        COUNT(*) as count
                    FROM inspection_submissions s
                    JOIN water_supplies ws ON s.supply_id = ws.id
                    WHERE s.submission_date >= ? AND ws.parish = ?
                    GROUP BY DATE(s.submission_date)
                    ORDER BY s.submission_date
                '''
                results = conn.execute(query, (start_date.strftime('%Y-%m-%d'), parish)).fetchall()

                # Convert to time series data
                time_series = []
                for row in results:
                    if row['avg_chlorine']:
                        timestamp = int(datetime.strptime(row['date'], '%Y-%m-%d').timestamp())
                        time_series.append({
                            'time': timestamp,
                            'value': float(row['avg_chlorine'])
                        })

                parish_data[parish] = {
                    'timeSeries': time_series,
                    'color': get_parish_color(parish),
                    'total_submissions': sum(row['count'] for row in results)
                }

            elif chart_type == 'visits':
                # Get visits data for this parish
                query = '''
                    SELECT
                        DATE(s.submission_date) as date,
                        SUM(s.visits) as total_visits,
                        COUNT(*) as count
                    FROM inspection_submissions s
                    JOIN water_supplies ws ON s.supply_id = ws.id
                    WHERE s.submission_date >= ? AND ws.parish = ?
                    GROUP BY DATE(s.submission_date)
                    ORDER BY s.submission_date
                '''
                results = conn.execute(query, (start_date.strftime('%Y-%m-%d'), parish)).fetchall()

                # Convert to time series data
                time_series = []
                for row in results:
                    timestamp = int(datetime.strptime(row['date'], '%Y-%m-%d').timestamp())
                    time_series.append({
                        'time': timestamp,
                        'value': float(row['total_visits'] or 0)
                    })

                parish_data[parish] = {
                    'timeSeries': time_series,
                    'color': get_parish_color(parish),
                    'total_submissions': sum(row['count'] for row in results)
                }

        conn.close()
        return jsonify(parish_data)

    except Exception as e:
        conn.close()
        print(f"Parish comparison error: {e}")
        return jsonify({'error': str(e)}), 500

def get_parish_color(parish):
    """Return consistent colors for each parish"""
    colors = {
        'Westmoreland': '#667eea',  # Blue
        'Trelawny': '#28a745',      # Green
        'Hanover': '#dc3545',       # Red
        'St. James': '#fd7e14'      # Orange
    }
    return colors.get(parish, '#6c757d')  # Default gray

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
            (supply_id, inspector_id, sampling_point_id, submission_date, visits, chlorine_total, chlorine_positive,
             chlorine_negative, chlorine_positive_range, chlorine_negative_range, bacteriological_positive,
             bacteriological_negative, bacteriological_pending, isolated_organism, remarks, facility_type)
            VALUES (?, ?, ?, date('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['supply_id'], session['user_id'], data.get('sampling_point_id'),
            data.get('visits', 0), data.get('chlorine_total', 0), data.get('chlorine_positive', 0),
            data.get('chlorine_negative', 0), data.get('chlorine_positive_range', ''),
            data.get('chlorine_negative_range', ''), data.get('bacteriological_positive', 0),
            data.get('bacteriological_negative', 0), data.get('bacteriological_pending', 0),
            data.get('isolated_organism', ''), data.get('remarks', ''), data.get('facility_type', '')
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
        SELECT s.*, ws.name as supply_name, ws.type, ws.agency,
               sp.name as sampling_point_name, sp.location as sampling_point_location
        FROM inspection_submissions s
        JOIN water_supplies ws ON s.supply_id = ws.id
        LEFT JOIN sampling_points sp ON s.sampling_point_id = sp.id
        WHERE s.inspector_id = ?
        ORDER BY s.created_at DESC
        LIMIT 10
    ''', (session['user_id'],)).fetchall()
    conn.close()

    return jsonify([dict(submission) for submission in submissions])

@app.route('/api/submissions')
def get_submissions():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    supply_id = request.args.get('supply_id')
    limit = request.args.get('limit', 10, type=int)

    conn = get_db_connection()

    if supply_id:
        submissions = conn.execute('''
            SELECT s.*, ws.name as supply_name, ws.type, ws.agency,
                   sp.name as sampling_point_name, sp.location as sampling_point_location
            FROM inspection_submissions s
            JOIN water_supplies ws ON s.supply_id = ws.id
            LEFT JOIN sampling_points sp ON s.sampling_point_id = sp.id
            WHERE s.supply_id = ?
            ORDER BY s.created_at DESC
            LIMIT ?
        ''', (supply_id, limit)).fetchall()
    else:
        submissions = conn.execute('''
            SELECT s.*, ws.name as supply_name, ws.type, ws.agency,
                   sp.name as sampling_point_name, sp.location as sampling_point_location
            FROM inspection_submissions s
            JOIN water_supplies ws ON s.supply_id = ws.id
            LEFT JOIN sampling_points sp ON s.sampling_point_id = sp.id
            ORDER BY s.created_at DESC
            LIMIT ?
        ''', (limit,)).fetchall()

    conn.close()

    return jsonify([dict(submission) for submission in submissions])

@app.route('/api/submission/<int:submission_id>')
def get_submission_details(submission_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    conn = get_db_connection()
    submission = conn.execute('''
        SELECT s.*, ws.name as supply_name, ws.type, ws.agency,
               sp.name as sampling_point_name, sp.location as sampling_point_location,
               u.full_name as inspector_name
        FROM inspection_submissions s
        JOIN water_supplies ws ON s.supply_id = ws.id
        LEFT JOIN sampling_points sp ON s.sampling_point_id = sp.id
        JOIN users u ON s.inspector_id = u.id
        WHERE s.id = ? AND s.inspector_id = ?
    ''', (submission_id, session['user_id'])).fetchone()
    conn.close()

    if not submission:
        return jsonify({'error': 'Submission not found'}), 404

    return jsonify(dict(submission))

@app.route('/api/submission/<int:submission_id>/download')
def download_submission(submission_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    conn = get_db_connection()
    submission = conn.execute('''
        SELECT s.*, ws.name as supply_name, ws.type, ws.agency,
               sp.name as sampling_point_name, sp.location as sampling_point_location,
               u.full_name as inspector_name
        FROM inspection_submissions s
        JOIN water_supplies ws ON s.supply_id = ws.id
        LEFT JOIN sampling_points sp ON s.sampling_point_id = sp.id
        JOIN users u ON s.inspector_id = u.id
        WHERE s.id = ? AND s.inspector_id = ?
    ''', (submission_id, session['user_id'])).fetchone()
    conn.close()

    if not submission:
        return jsonify({'error': 'Submission not found'}), 404

    # Generate HTML content for the submission
    html_content = generate_submission_html(dict(submission))

    # For now, return the HTML as a file download
    from flask import make_response
    response = make_response(html_content)
    response.headers['Content-Type'] = 'text/html'
    response.headers['Content-Disposition'] = f'attachment; filename=submission_{submission_id}.html'

    return response

def generate_submission_html(submission):
    # Format the submission date nicely
    from datetime import datetime
    created_date = datetime.strptime(submission['created_at'], '%Y-%m-%d %H:%M:%S').strftime('%B %d, %Y at %I:%M %p')

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Water Quality Inspection - {submission['supply_name']} - {submission['submission_date']}</title>
    <style>
        @media print {{
            body {{ margin: 0; }}
            .no-print {{ display: none; }}
        }}

        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
            line-height: 1.6;
        }}

        .form-container {{
            background: white;
            padding: 2rem;
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
        }}

        .header {{
            text-align: center;
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 3px solid #667eea;
        }}

        .header h1 {{
            color: #333;
            margin: 0 0 10px 0;
            font-size: 28px;
        }}

        .header p {{
            color: #666;
            margin: 5px 0;
            font-size: 16px;
        }}

        .selected-supply {{
            background: linear-gradient(135deg, #e3f2fd 0%, #f3e5f5 100%);
            padding: 1.5rem;
            border-radius: 8px;
            margin-bottom: 2rem;
            border-left: 5px solid #667eea;
        }}

        .selected-supply h3 {{
            margin: 0 0 8px 0;
            color: #333;
            font-size: 22px;
        }}

        .selected-supply p {{
            margin: 4px 0;
            color: #666;
        }}

        .form-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}

        .form-group {{
            margin-bottom: 1rem;
        }}

        .form-group label {{
            display: block;
            margin-bottom: 8px;
            color: #333;
            font-weight: 600;
            font-size: 14px;
        }}

        .form-value {{
            padding: 12px;
            border: 2px solid #ddd;
            border-radius: 6px;
            background: white;
            min-height: 20px;
            font-size: 16px;
        }}

        .test-section {{
            background: #f8f9fa;
            padding: 1.5rem;
            border-radius: 8px;
            margin-bottom: 1.5rem;
            border: 1px solid #e9ecef;
        }}

        .test-section h3 {{
            color: #333;
            margin-bottom: 1.5rem;
            font-size: 18px;
            border-bottom: 2px solid #dee2e6;
            padding-bottom: 8px;
        }}

        .test-inputs {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 1.5rem;
        }}

        .positive-field {{
            background: #d4edda !important;
            border-color: #28a745 !important;
            color: #155724;
        }}

        .negative-field {{
            background: #f8d7da !important;
            border-color: #dc3545 !important;
            color: #721c24;
        }}

        .pending-field {{
            background: #fff3cd !important;
            border-color: #ffc107 !important;
            color: #856404;
        }}

        .range-info {{
            color: #666;
            font-size: 13px;
            font-weight: bold;
            margin-top: 8px;
            padding: 4px 8px;
            background: rgba(0,0,0,0.05);
            border-radius: 4px;
        }}

        .footer {{
            text-align: center;
            margin-top: 3rem;
            padding-top: 2rem;
            border-top: 2px solid #eee;
            color: #666;
        }}

        .footer p {{
            margin: 8px 0;
        }}

        .print-button {{
            background: #667eea;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 16px;
            margin: 20px 0;
        }}

        .print-button:hover {{
            background: #5a6fd8;
        }}

        .submission-id {{
            position: absolute;
            top: 20px;
            right: 20px;
            background: #667eea;
            color: white;
            padding: 8px 12px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="submission-id">ID: {submission['id']}</div>

    <div class="form-container">
        <div class="header">
            <h1>Water Quality Inspection Report</h1>
            <p><strong>Inspector:</strong> {submission['inspector_name']}</p>
            <p><strong>Submission ID:</strong> #{submission['id']}</p>
        </div>

        <button onclick="window.print()" class="print-button no-print">🖨️ Print This Report</button>

        <div class="selected-supply">
            <h3>{submission['supply_name']}</h3>
            <p><strong>Agency:</strong> {submission['agency']} • <strong>Type:</strong> {submission['type'].title()} Supply</p>
            {f"<p><strong>Sampling Point:</strong> {submission['sampling_point_name']}" + (f" ({submission['sampling_point_location']})" if submission['sampling_point_location'] else "") + "</p>" if submission['sampling_point_name'] else ""}
        </div>

        <div class="form-grid">
            <div class="form-group">
                <label>Submission Date</label>
                <div class="form-value">{submission['submission_date']}</div>
            </div>
            <div class="form-group">
                <label>Number of Visits</label>
                <div class="form-value">{submission['visits']}</div>
            </div>
        </div>

        {f'''
        <div class="test-section">
            <h3>Chlorine Residual Tests (Treated Supply)</h3>
            <div class="test-inputs">
                <div class="form-group">
                    <label>Total Tests</label>
                    <div class="form-value" style="background: #f8f9fa; border-color: #6c757d;">{submission['chlorine_total']}</div>
                </div>
                <div class="form-group">
                    <label>Positive Results</label>
                    <div class="form-value positive-field">{submission['chlorine_positive']}</div>
                    {f'<div class="range-info">Range: {submission["chlorine_positive_range"]}</div>' if submission['chlorine_positive_range'] else ''}
                </div>
                <div class="form-group">
                    <label>Negative Results</label>
                    <div class="form-value negative-field">{submission['chlorine_negative']}</div>
                    {f'<div class="range-info">Range: {submission["chlorine_negative_range"]}</div>' if submission['chlorine_negative_range'] else ''}
                </div>
            </div>
        </div>
        ''' if submission['type'] == 'treated' else ''}

        <div class="test-section">
            <h3>Bacteriological Tests</h3>
            <div class="test-inputs">
                <div class="form-group">
                    <label>Positive Results</label>
                    <div class="form-value positive-field">{submission['bacteriological_positive']}</div>
                    {f'<div class="range-info">Isolated Organism: {submission["isolated_organism"]}</div>' if submission['isolated_organism'] else ''}
                </div>
                <div class="form-group">
                    <label>Negative Results</label>
                    <div class="form-value negative-field">{submission['bacteriological_negative']}</div>
                </div>
                <div class="form-group">
                    <label>Pending Results</label>
                    <div class="form-value pending-field">{submission['bacteriological_pending']}</div>
                </div>
            </div>
        </div>

        {f'''
        <div class="test-section">
            <h3>Inspector Remarks</h3>
            <div class="form-group">
                <div class="form-value" style="min-height: 80px; white-space: pre-wrap;">{submission['remarks']}</div>
            </div>
        </div>
        ''' if submission['remarks'] else ''}

        <div class="footer">
            <p><strong>Report Generated:</strong> {created_date}</p>
            <p><strong>Water Quality Monitoring System</strong></p>
            <p>This is an official inspection record.</p>
        </div>
    </div>

    <script>
        // Auto-focus for better user experience
        document.addEventListener('DOMContentLoaded', function() {{
            console.log('Water Quality Inspection Report loaded successfully');
        }});
    </script>
</body>
</html>'''

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

# Task Management API Routes
@app.route('/api/admin/tasks', methods=['GET'])
def get_admin_tasks():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    conn = get_db_connection()
    tasks = conn.execute('''
        SELECT t.*,
               u_assigned.full_name as assignee_name,
               u_assigned.username as assignee_username,
               u_created.full_name as created_by_name,
               ws.name as supply_name
        FROM inspector_tasks t
        JOIN users u_assigned ON t.assigned_to_id = u_assigned.id
        JOIN users u_created ON t.created_by_id = u_created.id
        LEFT JOIN water_supplies ws ON t.supply_id = ws.id
        ORDER BY t.created_at DESC
    ''').fetchall()
    conn.close()

    return jsonify([dict(task) for task in tasks])

@app.route('/api/admin/tasks', methods=['POST'])
def create_admin_task():
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'error': 'Not authorized'}), 403

    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO inspector_tasks
            (title, description, assigned_to_id, supply_id, priority, due_date, created_by_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['title'],
            data.get('description', ''),
            data['inspector_id'],
            data.get('supply_id'),
            data['priority'],
            data['due_date'],
            session['user_id']
        ))

        task_id = cursor.lastrowid
        conn.commit()

        # Get the created task with joined data
        task = cursor.execute('''
            SELECT t.*,
                   u_assigned.full_name as assignee_name,
                   u_assigned.username as assignee_username,
                   u_created.full_name as created_by_name,
                   ws.name as supply_name
            FROM inspector_tasks t
            JOIN users u_assigned ON t.assigned_to_id = u_assigned.id
            JOIN users u_created ON t.created_by_id = u_created.id
            LEFT JOIN water_supplies ws ON t.supply_id = ws.id
            WHERE t.id = ?
        ''', (task_id,)).fetchone()

        conn.close()

        # Emit real-time update
        socketio.emit('new_task', dict(task), room='admin')

        return jsonify({'success': True, 'task': dict(task)})

    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/inspector/tasks', methods=['GET'])
def get_inspector_tasks():
    """Get tasks assigned to the current user (works for both inspectors and admins)"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    conn = get_db_connection()
    tasks = conn.execute('''
        SELECT t.*,
               u_created.full_name as assigned_by,
               ws.name as supply_name,
               ws.type as supply_type
        FROM inspector_tasks t
        JOIN users u_created ON t.created_by_id = u_created.id
        LEFT JOIN water_supplies ws ON t.supply_id = ws.id
        WHERE t.assigned_to_id = ?
        ORDER BY t.created_at DESC
    ''', (session['user_id'],)).fetchall()
    conn.close()

    return jsonify([dict(task) for task in tasks])

@app.route('/api/my-tasks', methods=['GET'])
def get_my_tasks():
    """Alternative endpoint name that's clearer for all user types"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    conn = get_db_connection()
    tasks = conn.execute('''
        SELECT t.*,
               u_created.full_name as assigned_by,
               ws.name as supply_name,
               ws.type as supply_type
        FROM inspector_tasks t
        JOIN users u_created ON t.created_by_id = u_created.id
        LEFT JOIN water_supplies ws ON t.supply_id = ws.id
        WHERE t.assigned_to_id = ?
        ORDER BY t.created_at DESC
    ''', (session['user_id'],)).fetchall()
    conn.close()

    return jsonify([dict(task) for task in tasks])

@app.route('/api/inspector/tasks/<int:task_id>/accept', methods=['POST'])
def accept_task(task_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            UPDATE inspector_tasks
            SET status = 'accepted', updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND assigned_to_id = ?
        ''', (task_id, session['user_id']))

        conn.commit()
        conn.close()

        return jsonify({'success': True})

    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/inspector/tasks/<int:task_id>/reject', methods=['POST'])
def reject_task(task_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            UPDATE inspector_tasks
            SET status = 'rejected', updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND assigned_to_id = ?
        ''', (task_id, session['user_id']))

        conn.commit()
        conn.close()

        return jsonify({'success': True})

    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/inspector/tasks/<int:task_id>/start', methods=['POST'])
def start_task(task_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            UPDATE inspector_tasks
            SET status = 'in_progress', updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND assigned_to_id = ?
        ''', (task_id, session['user_id']))

        conn.commit()
        conn.close()

        return jsonify({'success': True})

    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/inspector/tasks/<int:task_id>/complete', methods=['POST'])
def complete_task(task_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            UPDATE inspector_tasks
            SET status = 'completed', updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND assigned_to_id = ?
        ''', (task_id, session['user_id']))

        conn.commit()
        conn.close()

        return jsonify({'success': True})

    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/inspectors', methods=['GET'])
def get_inspectors():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    conn = get_db_connection()
    # Return ALL users (both inspectors and admins) for task assignment
    users = conn.execute('''
        SELECT id, username, full_name, role, COALESCE(parish, 'Westmoreland') as parish
        FROM users
        ORDER BY role DESC, full_name
    ''').fetchall()
    conn.close()

    return jsonify([dict(user) for user in users])

@app.route('/api/users', methods=['GET'])
def get_all_users():
    """Dedicated endpoint for getting all users"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    conn = get_db_connection()
    users = conn.execute('''
        SELECT id, username, full_name, role, COALESCE(parish, 'Westmoreland') as parish
        FROM users
        ORDER BY role DESC, full_name
    ''').fetchall()
    conn.close()

    return jsonify([dict(user) for user in users])

@app.route('/api/admin/users', methods=['POST'])
def create_user():
    """Create a new user with parish association"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403

    data = request.json
    username = data.get('username')
    password = data.get('password')
    role = data.get('role')
    full_name = data.get('full_name')
    parish = data.get('parish')

    # Validate required fields
    if not all([username, password, role, full_name, parish]):
        return jsonify({'error': 'All fields are required'}), 400

    # Validate role
    if role not in ['inspector', 'admin']:
        return jsonify({'error': 'Invalid role'}), 400

    # Validate parish
    valid_parishes = ['Westmoreland', 'Trelawny', 'Hanover', 'St. James']
    if parish not in valid_parishes:
        return jsonify({'error': 'Invalid parish'}), 400

    # Hash password
    password_hash = hashlib.sha256(password.encode()).hexdigest()

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO users (username, password_hash, role, full_name, parish)
            VALUES (?, ?, ?, ?, ?)
        ''', (username, password_hash, role, full_name, parish))
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()

        return jsonify({
            'success': True,
            'message': f'User {username} created successfully',
            'user_id': user_id
        }), 201
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Username already exists'}), 409
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500

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

    # Add sample data for testing
    add_sample_data()

    if debug:
        # Development mode
        socketio.run(app, host='0.0.0.0', port=port, debug=True, allow_unsafe_werkzeug=True)
    else:
        # Production mode - but allow unsafe werkzeug for local testing and Render deployment
        socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)