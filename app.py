from flask import Flask, request, jsonify, session, redirect, url_for, render_template_string, render_template, send_file
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.utils import secure_filename
import sqlite3
import hashlib
from datetime import datetime, date, timedelta
import json
import os
import urllib.parse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'water-monitoring-secret-key-2024'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)  # Sessions last 7 days
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'static/documents'

# Allowed file extensions for uploads
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt', 'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
socketio = SocketIO(app, cors_allowed_origins="*")

# Database configuration
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    # Production: Use PostgreSQL
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        USE_POSTGRESQL = True
        print("[STARTUP] Using PostgreSQL database")

        # Parse DATABASE_URL for psycopg2
        parsed = urllib.parse.urlparse(DATABASE_URL)
        DB_CONFIG = {
            'host': parsed.hostname,
            'port': parsed.port,
            'database': parsed.path[1:],  # Remove leading '/'
            'user': parsed.username,
            'password': parsed.password,
            'sslmode': 'require'
        }
    except ImportError:
        print("[ERROR] psycopg2 not installed. Install with: pip install psycopg2-binary")
        USE_POSTGRESQL = False
        DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'water_monitoring.db')
else:
    # Development: Use SQLite
    USE_POSTGRESQL = False
    DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'water_monitoring.db')
    print("[STARTUP] Using SQLite database")

def init_db():
    try:
        conn = get_db_connection()

        if USE_POSTGRESQL:
            cursor = conn.cursor()

            # PostgreSQL-specific table creation
            # Users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(255) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    role VARCHAR(50) NOT NULL CHECK (role IN ('inspector', 'admin')),
                    full_name VARCHAR(255) NOT NULL,
                    parish VARCHAR(100) NOT NULL DEFAULT 'Westmoreland',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Add parish column to existing users table if it doesn't exist
            try:
                cursor.execute('ALTER TABLE users ADD COLUMN parish VARCHAR(100) DEFAULT %s', ('Westmoreland',))
            except Exception:
                # Column already exists
                pass

            # Update existing users without parish to have Westmoreland
            cursor.execute("UPDATE users SET parish = %s WHERE parish IS NULL OR parish = ''", ('Westmoreland',))

            # Water supplies table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS water_supplies (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    type VARCHAR(50) NOT NULL CHECK (type IN ('treated', 'untreated')),
                    agency VARCHAR(100) NOT NULL,
                    location VARCHAR(255),
                    parish VARCHAR(100) DEFAULT 'Westmoreland',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Monthly supply data table for accumulative reporting
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS monthly_supply_data (
                    id SERIAL PRIMARY KEY,
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
                    id SERIAL PRIMARY KEY,
                    supply_id INTEGER NOT NULL,
                    inspector_id INTEGER NOT NULL,
                    sampling_point_id INTEGER,
                    submission_date DATE NOT NULL,
                    visits INTEGER DEFAULT 0,
                    chlorine_total INTEGER DEFAULT 0,
                    chlorine_positive INTEGER DEFAULT 0,
                    chlorine_negative INTEGER DEFAULT 0,
                    chlorine_positive_range VARCHAR(50),
                    chlorine_negative_range VARCHAR(50),
                    bacteriological_positive INTEGER DEFAULT 0,
                    bacteriological_negative INTEGER DEFAULT 0,
                    bacteriological_pending INTEGER DEFAULT 0,
                    bacteriological_rejected INTEGER DEFAULT 0,
                    bacteriological_broken INTEGER DEFAULT 0,
                    bacteriological_rejected_reason TEXT,
                    bacteriological_broken_reason TEXT,
                    bacteriological_status VARCHAR(20) DEFAULT 'pending',
                    isolated_organism VARCHAR(255),
                    ph_satisfactory INTEGER DEFAULT 0,
                    ph_non_satisfactory INTEGER DEFAULT 0,
                    ph_non_satisfactory_params TEXT,
                    bacteriological_positive_status VARCHAR(50),
                    bacteriological_negative_status VARCHAR(50),
                    chemical_satisfactory INTEGER DEFAULT 0,
                    chemical_non_satisfactory INTEGER DEFAULT 0,
                    chemical_non_satisfactory_params TEXT,
                    turbidity_satisfactory INTEGER DEFAULT 0,
                    turbidity_non_satisfactory INTEGER DEFAULT 0,
                    temperature_satisfactory INTEGER DEFAULT 0,
                    temperature_non_satisfactory INTEGER DEFAULT 0,
                    remarks TEXT,
                    facility_type VARCHAR(100),
                    water_source_type VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (supply_id) REFERENCES water_supplies (id),
                    FOREIGN KEY (inspector_id) REFERENCES users (id),
                    FOREIGN KEY (sampling_point_id) REFERENCES sampling_points (id)
                )
            ''')

            # Inspector signatures table for tracking multiple inspectors per submission
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS inspector_signatures (
                    id SERIAL PRIMARY KEY,
                    submission_id INTEGER NOT NULL,
                    inspector_id INTEGER NOT NULL,
                    action_type VARCHAR(50) NOT NULL,
                    signature_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    notes TEXT,
                    FOREIGN KEY (submission_id) REFERENCES inspection_submissions (id),
                    FOREIGN KEY (inspector_id) REFERENCES users (id)
                )
            ''')

            # Sampling points table for water supplies
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sampling_points (
                    id SERIAL PRIMARY KEY,
                    supply_id INTEGER NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    location VARCHAR(255),
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (supply_id) REFERENCES water_supplies (id)
                )
            ''')

            # Tasks table for inspector assignments
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS inspector_tasks (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    description TEXT,
                    assigned_to_id INTEGER NOT NULL,
                    supply_id INTEGER,
                    priority VARCHAR(50) NOT NULL CHECK (priority IN ('Low', 'Medium', 'High', 'Urgent')),
                    due_date DATE NOT NULL,
                    status VARCHAR(50) NOT NULL CHECK (status IN ('pending', 'accepted', 'in_progress', 'completed', 'rejected')) DEFAULT 'pending',
                    created_by_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (assigned_to_id) REFERENCES users (id),
                    FOREIGN KEY (supply_id) REFERENCES water_supplies (id),
                    FOREIGN KEY (created_by_id) REFERENCES users (id)
                )
            ''')

            # Documents table for Tool Kit
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS documents (
                    id SERIAL PRIMARY KEY,
                    filename VARCHAR(255) NOT NULL,
                    original_name VARCHAR(255) NOT NULL,
                    file_path TEXT NOT NULL,
                    uploaded_by INTEGER NOT NULL,
                    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (uploaded_by) REFERENCES users (id)
                )
            ''')

        else:
            # SQLite-specific table creation (existing code)
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
                    parish TEXT DEFAULT 'Westmoreland',
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
                    bacteriological_rejected INTEGER DEFAULT 0,
                    bacteriological_broken INTEGER DEFAULT 0,
                    bacteriological_rejected_reason TEXT,
                    bacteriological_broken_reason TEXT,
                    bacteriological_status TEXT DEFAULT 'pending',
                    isolated_organism TEXT,
                    ph_satisfactory INTEGER DEFAULT 0,
                    ph_non_satisfactory INTEGER DEFAULT 0,
                    ph_non_satisfactory_params TEXT,
                    bacteriological_positive_status TEXT,
                    bacteriological_negative_status TEXT,
                    chemical_satisfactory INTEGER DEFAULT 0,
                    chemical_non_satisfactory INTEGER DEFAULT 0,
                    chemical_non_satisfactory_params TEXT,
                    turbidity_satisfactory INTEGER DEFAULT 0,
                    turbidity_non_satisfactory INTEGER DEFAULT 0,
                    temperature_satisfactory INTEGER DEFAULT 0,
                    temperature_non_satisfactory INTEGER DEFAULT 0,
                    remarks TEXT,
                    facility_type TEXT,
                    water_source_type TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (supply_id) REFERENCES water_supplies (id),
                    FOREIGN KEY (inspector_id) REFERENCES users (id),
                    FOREIGN KEY (sampling_point_id) REFERENCES sampling_points (id)
                )
            ''')

            # Inspector signatures table for tracking multiple inspectors per submission
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS inspector_signatures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    submission_id INTEGER NOT NULL,
                    inspector_id INTEGER NOT NULL,
                    action_type TEXT NOT NULL,
                    signature_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    notes TEXT,
                    FOREIGN KEY (submission_id) REFERENCES inspection_submissions (id),
                    FOREIGN KEY (inspector_id) REFERENCES users (id)
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

            # Documents table for Tool Kit
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    uploaded_by INTEGER NOT NULL,
                    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (uploaded_by) REFERENCES users (id)
                )
            ''')

        # Populate initial data using shared function
        _populate_initial_data(conn, cursor)

        conn.commit()
        if USE_POSTGRESQL:
            cursor.close()
        conn.close()
        print(f"Database initialized successfully using {'PostgreSQL' if USE_POSTGRESQL else 'SQLite'}")

    except Exception as e:
        print(f"Error initializing database: {e}")
        if 'conn' in locals():
            if USE_POSTGRESQL:
                conn.rollback()
            conn.close()
        raise

def _populate_initial_data(conn, cursor):
    """Populate initial data for both PostgreSQL and SQLite"""
    import hashlib
    from water_supplies_data import get_all_supplies

    # Insert default users
    if USE_POSTGRESQL:
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
    else:
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]

    if user_count == 0:
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
            # Hanover Inspectors (password: inspector123)
            ('hanover1', hashlib.sha256('inspector123'.encode()).hexdigest(), 'inspector', 'Hanover Inspector A', 'Hanover'),
            ('hanover2', hashlib.sha256('inspector123'.encode()).hexdigest(), 'inspector', 'Hanover Inspector B', 'Hanover'),
            ('hanover3', hashlib.sha256('inspector123'.encode()).hexdigest(), 'inspector', 'Hanover Inspector C', 'Hanover'),
            # Hanover Admin (password: admin123)
            ('hanover_admin', hashlib.sha256('admin123'.encode()).hexdigest(), 'admin', 'Hanover Administrator', 'Hanover'),
            # St. James Inspectors (password: inspector123)
            ('stjames1', hashlib.sha256('inspector123'.encode()).hexdigest(), 'inspector', 'St. James Inspector A', 'St. James'),
            ('stjames2', hashlib.sha256('inspector123'.encode()).hexdigest(), 'inspector', 'St. James Inspector B', 'St. James'),
            ('stjames3', hashlib.sha256('inspector123'.encode()).hexdigest(), 'inspector', 'St. James Inspector C', 'St. James'),
            # St. James Admin (password: admin123)
            ('stjames_admin', hashlib.sha256('admin123'.encode()).hexdigest(), 'admin', 'St. James Administrator', 'St. James'),
        ]

        if USE_POSTGRESQL:
            cursor.executemany('''
                INSERT INTO users (username, password_hash, role, full_name, parish)
                VALUES (%s, %s, %s, %s, %s)
            ''', test_users)
        else:
            cursor.executemany('''
                INSERT INTO users (username, password_hash, role, full_name, parish)
                VALUES (?, ?, ?, ?, ?)
            ''', test_users)

    # Insert water supplies from the shared data module
    if USE_POSTGRESQL:
        cursor.execute("SELECT COUNT(*) FROM water_supplies")
        supply_count = cursor.fetchone()[0]
    else:
        cursor.execute("SELECT COUNT(*) FROM water_supplies")
        supply_count = cursor.fetchone()[0]

    if supply_count == 0:
        supplies = get_all_supplies()

        if USE_POSTGRESQL:
            cursor.executemany('''
                INSERT INTO water_supplies (name, type, agency, location, parish)
                VALUES (%s, %s, %s, %s, %s)
            ''', supplies)
        else:
            cursor.executemany('''
                INSERT INTO water_supplies (name, type, agency, location, parish)
                VALUES (?, ?, ?, ?, ?)
            ''', supplies)

    # Insert sampling points for all water supplies (always recreate)
    # First, clear existing sampling points
    if USE_POSTGRESQL:
        cursor.execute("DELETE FROM sampling_points")
    else:
        cursor.execute("DELETE FROM sampling_points")

    # Always insert sampling points
    sampling_points = []

    # Helper function to get supply ID
    def get_supply_id(name):
        if USE_POSTGRESQL:
            cursor.execute('SELECT id FROM water_supplies WHERE name = %s', (name,))
        else:
            cursor.execute('SELECT id FROM water_supplies WHERE name = ?', (name,))
        result = cursor.fetchone()
        return result[0] if result else None

    # Westmoreland - All water source sampling points (47 total locations)
    westmoreland_sources = {
        'Roaring River I & II': [
            'Tap @ Health Department (old plant)',
            'Tap @ Hospital Storage tank (old plant)',
            'Standpipe @ 135 Dalling Street (old plant)',
            'Tap @ Loading Bay, Petersfield (old plant)',
            'Standpipe @ Lower Darliston (new plant)',
            'Standpipe @ Carawina Road (old plant)',
            'Standpipe @ Roaring River District (old plant)',
            'Tap @ Shop, Michael Smith Ave (new plant)',
            'Tap @ Dud\'s Bar, Whithorn (new plant)'
        ],
        'Bullstrode': [
            'Standpipe @ Barneyside All Age',
            'Standpipe @ Ridge Bridge, Broughton',
            'Standpipe @ Delveland H/C',
            'Standpipe @ Old Hope pump station',
            'Tap @ Little London H/C',
            'Tap @ Grange Hill H/C',
            'Standpipe @ Camp Savanna, near Malcolm\'s Garage',
            'Tap @ Ms. Daisy\'s Grocery, Big Bridge'
        ],
        'Dean\'s Valley': [
            'Standpipe @ Dean\'s Valley main road',
            'Standpipe @ Heavy Sands'
        ],
        'Carawina': [
            'Tap @ Grace Food Processor, Administration area',
            'Tap @ Weddy\'s Slaughter facility'
        ],
        'Williamsfield/Venture': [
            'Standpipe @ Content main road',
            'Standpipe @ Grange main road',
            'Standpipe @ Kevin\'s Grocery, Fort William',
            'Standpipe @ Williamsfield H/C',
            'Standpipe @ Mayfield Fall',
            'Tap @ Grange Square, Shop and Grocery'
        ],
        'Bluefields': [
            'Standpipe @ Bluefields Beach Park',
            'Standpipe @ Farm',
            'Standpipe @ Culloden Square',
            'Standpipe @ Whitehouse H/C'
        ],
        'Jerusalem Mountains': [
            'Tap @ Side of SDA, Jerusalem Mountains',
            'Tap @ Herring Piece, Anderson\'s Property'
        ],
        'Cave': [
            'Tap @ Cave Square'
        ],
        'Friendship': [
            'Standpipe @ Friendship main road',
            'Standpipe @ SDA Church',
            'Tap @ Main road, beside Strawberry School',
            'Tap @ Braham',
            'Tap @ Friendship School'
        ],
        'Negril–Logwood': [
            'Standpipe @ Sheffield P.O',
            'Tap @ Negril H/C',
            'Standpipe @ Spring Garden (main road)',
            'Standpipe @ Retreat Square'
        ],
        'Bethel Town/Cambridge': [
            'Tap @ Bethel Town H/C',
            'Tap @ Skepie\'s premises, Galloway'
        ],
        'Petersville': [
            '1st standpipe from pumping station',
            'Standpipe @ Long Hill, Near Culvert'
        ],
        'Dantrout': [
            'Standpipe @ Marchmont Road Square',
            'Tap @ St. Leonard\'s H/C',
            'Standpipe @ Beside St. Leonard\'s H/C'
        ]
    }

    for source_name, sampling_points_list in westmoreland_sources.items():
        supply_id = get_supply_id(source_name)
        if supply_id:
            for point_name in sampling_points_list:
                location_key = source_name.lower().replace(' ', '_').replace('/', '_').replace('&', '').replace('–', '_')
                sampling_points.append((supply_id, point_name, location_key, f'{point_name} sampling point for {source_name}'))

    # Hanover - HMC Supplies (34 supplies - all untreated, source sampling points)
    hmc_supplies = [
        'Claremont Catchment', 'Thompson Hill Catchment', 'Upper Rock Spring', 'Success Catchment',
        'Bamboo Spring', 'Jericho Spring', 'Lethe Spring', 'Welcome Spring', 'Knockalva Catchment',
        'Flamstead Spring', 'Pierces Village Catchment', 'Cold Spring', 'Rejion Tank', 'Rejoin Catchment',
        'Chovey Hole', 'Content Catchment', 'St Simon Spring', 'Donalva Spring', 'Sawpit Spring',
        'Patty Hill Spring', 'Woodsville Catchment', 'Dias Tank', 'Anderson Spring', 'Bamboo Roadside Overflow',
        'Axe-and-Adze Catchment', 'Soja Spring', 'Castle Hyde Catchment', 'Medley Spring', 'Craig Nathan',
        'Jabez Catchment', 'Rockfoot Reservoir', 'Burntside Spring', 'Old Cold Spring', 'Spring Georgia'
    ]

    for supply_name in hmc_supplies:
        supply_id = get_supply_id(supply_name)
        if supply_id:
            sampling_points.append((supply_id, 'Source', supply_name.lower().replace(' ', '_'), f'Source sampling point for {supply_name}'))
            # Special case for St Simon Spring - has additional sampling point
            if supply_name == 'St Simon Spring':
                sampling_points.append((supply_id, 'St. Simon Community Tank', 'st_simon', 'St. Simon Community Tank sampling point'))

    # Hanover - NWC Supplies (5 supplies - all treated)
    nwc_hanover_supplies = {
        'Logwood': ['D/T', 'Logwood H/C', 'Green Island H/C', 'Green Island S/P', 'Cave Valley H/C'],
        'New Milns': ['D/T', 'New Milns S/P'],
        'Kendal': ['D/T', 'Kendal Cross Road', 'Jehovah Witness S/P', 'Friendship S/P', 'Grange S/P', 'Neva Shop-Cessnock'],
        'Shettlewood Hanover': ['D/T', 'Ramble H/C', 'Chester Castle H/C', 'Mt. Ward Primary', 'Knockalva Polythecnic', 'Miles Town S/P', 'Colhorn Enterprise', 'Brayhorn Enterprise', 'West Haven Chidren\'s Home', 'Arawak Restaurant', 'Border Jerk', 'Mt. Peto H/C'],
        'Great River - St. James': ['Hopewell H/C', 'Sandy bay H/C', 'Kew Bridge', 'Hanover H/D', 'First Hill S/P', 'Noel Holmes Hospital (X3)', 'Copperwood Farms', 'Dorcey James Property', 'NWC Lucea Loading Bay', 'Hugh Garwood Premises', 'McQuaire/Woodland Relift Station']
    }

    for supply_name, sample_points in nwc_hanover_supplies.items():
        supply_id = get_supply_id(supply_name)
        if supply_id:
            for point in sample_points:
                sampling_points.append((supply_id, point, supply_name.lower().replace(' ', '_'), f'{point} sampling point for {supply_name}'))

    # Hanover - Private Supplies
    private_hanover_supplies = {
        'Tryall Club': ['D/T', 'Tryall Market'],
        'Vivid Water Store': ['Alkaline tap'],
        'Aquacity Water Store': ['Mineral Tap'],
        'M&B Water Store': ['Alkaline Tap'],
        'Quenched Water Store': ['Purified Tap'],
        'Epic Blue': ['Alkaline Tap'],
        'Dynasty Water Store': ['Alkaline Tap'],
        'Valley Dew': ['Purified Tap'],
        'Jus Chill': ['Closed (Not operational)'],
        'Royalton Resorts': ['Sample Point 1', 'Sample Point 2', 'Sample Point 3', 'Sample Point 4', 'Sample Point 5', 'Sample Point 6', 'Sample Point 7'],
        'Sandals Negril': ['Sample Point 1', 'Sample Point 2', 'Sample Point 3'],
        'Couples Negril': ['Sample Point 1', 'Sample Point 2', 'Sample Point 3'],
        'Sunset At The Palms': ['Sample Point 1', 'Sample Point 2', 'Sample Point 3'],
        'Azul Resort': ['Sample Point 1', 'Sample Point 2', 'Sample Point 3'],
        'Round Hill Resort': ['Sample Point 1', 'Sample Point 2', 'Sample Point 3'],
        'Hedonism II': ['Sample Point 1', 'Sample Point 2', 'Sample Point 3'],
        'Riu Tropical Bay': ['Sample Point 1', 'Sample Point 2', 'Sample Point 3'],
        'Riu Jamiecotel': ['Sample Point 1', 'Sample Point 2', 'Sample Point 3']
    }

    for supply_name, sample_points in private_hanover_supplies.items():
        supply_id = get_supply_id(supply_name)
        if supply_id:
            for point in sample_points:
                sampling_points.append((supply_id, point, supply_name.lower().replace(' ', '_'), f'{point} sampling point for {supply_name}'))

    # Trelawny - NWC Supplies (match exact database names from current database)
    trelawny_nwc_supplies = {
        'Rio Bueno': ['Tap @ Market', 'Standpipe @ Main Road', 'Tap @ Community Centre'],
        'Duncans': ['Plant', 'Tap @ Square', 'Standpipe @ Hill'],
        'Falmouth': ['Tap @ Hospital', 'Standpipe @ Market', 'Plant'],
        'Wakefield': ['Plant #1', 'Plant #2', 'Tap @ Storage Tank'],
        'Bounty Hall': ['Plant', 'Tap @ Main Road', 'Standpipe @ Square'],
        'Springvale': ['Tap @ Community Centre', 'Plant', 'Standpipe @ Church'],
        'Albert Town': ['Plant', 'Tap @ Square', 'Standpipe @ School'],
        'Silver Sands': ['Plant', 'Tap @ Resort', 'Standpipe @ Beach'],
        'Lorrimers': ['Plant', 'Tap @ Main Road', 'Standpipe @ Square'],
        'Bengal': ['Plant', 'Tap @ Community Centre', 'Standpipe @ Market'],
        'Martha Brae': ['Plant #1', 'Plant #2', 'Standpipe @ Coopers Pen'],
        'Clarks Town': ['Plant', 'Tap @ Main Road Kinloss', 'Standpipe @ Square'],
        'Wait-a-Bit': ['Plant', 'Tap @ Health Centre', 'Standpipe @ Market'],
        'Deeside': ['Plant', 'Tap @ Community Centre', 'Standpipe @ Main Road'],
        'Sherwood Content': ['Plant', 'Tap @ Square', 'Standpipe @ School'],
        'Salem': ['Plant', 'Tap @ Main Road', 'Standpipe @ Church'],
        'Refuge': ['Plant', 'Tap @ Community Centre', 'Standpipe @ Market'],
        'Ulster Spring': ['Plant', 'Tap @ Health Centre', 'Standpipe @ Square'],
        'Good Hope': ['Plant', 'Tap @ Main Road', 'Standpipe @ Resort'],
        'Bunkers Hill': ['Plant', 'Tap @ Community Centre', 'Standpipe @ Hill'],
        'Kettering': ['Plant', 'Tap @ Main Road', 'Standpipe @ Market'],
        'Troy': ['Plant', 'Tap @ Troy Square', 'Standpipe @ School'],
        'Granville': ['Plant', 'Tap @ Community Centre', 'Standpipe @ Main Road'],
        'Rock': ['Plant', 'Tap @ Health Centre', 'Standpipe @ Market'],
        'Garlands': ['Plant', 'Tap @ Main Road', 'Standpipe @ Square'],
        'Harmony Cove Resort': ['Plant', 'Tap @ Kitchen', 'Tap @ Bar', 'Tap @ Pool'],
        'Grand Palladium Resort': ['Plant', 'Tap @ Kitchen', 'Tap @ Bar', 'Tap @ Pool'],
        'Trelawny Beach Hotel': ['Plant', 'Tap @ Kitchen', 'Tap @ Bar', 'Tap @ Pool'],
        'Burwood Beach Resort': ['Plant', 'Tap @ Kitchen', 'Tap @ Bar', 'Tap @ Pool']
    }

    for supply_name, sample_points in trelawny_nwc_supplies.items():
        supply_id = get_supply_id(supply_name)
        if supply_id:
            for point in sample_points:
                sampling_points.append((supply_id, point, supply_name.lower().replace(' ', '_'), f'{point} sampling point for {supply_name}'))

    # Trelawny - PC Treated Supplies (match exact database names from current database)
    trelawny_pc_supplies = {
        'Mahogany Hall': ['Plant'],
        'Sawyers RWCT': ['Plant'],
        'Burke RWCT': ['Plant'],
        'Alps RWCT': ['Plant'],
        'Lorrimer\'s RWCT': ['Plant (UNTREATED)'],  # This is the untreated one
        'Wilson\'s Run RWCT': ['Plant'],
        'Huie': ['Plant'],
        'Stettin': ['Tap adj. Hardware Store'],
        'John Daggie': ['Tap @ storage tank'],
        'Campbell\'s Spring': ['Plant'],
        'Gager/Spring Garden': ['Tap opp. Pingue\'s Place'],
        'Freemans Hall': ['Plant'],  # Not specified in original data
        'Stewart Town': ['Plant']   # Not specified in original data
    }

    for supply_name, sample_points in trelawny_pc_supplies.items():
        supply_id = get_supply_id(supply_name)
        if supply_id:
            for point in sample_points:
                sampling_points.append((supply_id, point, supply_name.lower().replace(' ', '_'), f'{point} sampling point for {supply_name}'))

    # Trelawny - Private Supplies (match exact database names from current database)
    trelawny_private_supplies = {
        'Lobster Bowl': ['Kitchen'],
        'Rafters Village': ['Tap @ Bar'],
        'Good Hope/Chukka': ['Tap @ Bar'],
        'Tank-Weld': ['Tap @ Roundabout'],
        'Braco Resort': ['Plant'],  # Not specified in original data
        'Ocean Coral Spring Hotel': ['Plant'],  # Not specified in original data
        'Bamboo Beach': ['Plant']   # Not specified in original data
    }

    for supply_name, sample_points in trelawny_private_supplies.items():
        supply_id = get_supply_id(supply_name)
        if supply_id:
            for point in sample_points:
                sampling_points.append((supply_id, point, supply_name.lower().replace(' ', '_'), f'{point} sampling point for {supply_name}'))

    # Trelawny - MOH Health Centres (match exact database names from current database)
    trelawny_moh_supplies = {
        'Rio Bueno Health Centre': ['Tap @ Health Centre'],
        'Sherwood Content Health Centre': ['Tap @ Health Centre'],
        'Ulster Spring': ['Tap @ Health Centre'],  # MOH version (there's also NWC version)
        'Albert Town Health Centre': ['Tap @ Health Centre'],
        'Rock Spring Health Centre': ['Tap @ Health Centre'],
        'Warsop Health Centre': ['Tap @ Health Centre'],
        'Wait-A-Bit Health Centre': ['Tap @ Health Centre']
    }

    for supply_name, sample_points in trelawny_moh_supplies.items():
        supply_id = get_supply_id(supply_name)
        if supply_id:
            for point in sample_points:
                sampling_points.append((supply_id, point, supply_name.lower().replace(' ', '_'), f'{point} sampling point for {supply_name}'))

    # Insert all sampling points
    if sampling_points:
        if USE_POSTGRESQL:
            cursor.executemany('''
                INSERT INTO sampling_points (supply_id, name, location, description)
                VALUES (%s, %s, %s, %s)
            ''', sampling_points)
        else:
            cursor.executemany('''
                INSERT INTO sampling_points (supply_id, name, location, description)
                VALUES (?, ?, ?, ?)
            ''', sampling_points)

def get_db_connection():
    if USE_POSTGRESQL:
        try:
            conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
            return conn
        except Exception as e:
            print(f"[ERROR] PostgreSQL connection failed: {e}")
            raise
    else:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        return conn

def execute_query(query, params=None, fetch=None):
    """
    Universal query executor that handles both PostgreSQL and SQLite
    fetch options: None, 'one', 'all'
    """
    conn = get_db_connection()
    try:
        if USE_POSTGRESQL:
            with conn.cursor() as cursor:
                cursor.execute(query, params or [])
                if fetch == 'one':
                    return cursor.fetchone()
                elif fetch == 'all':
                    return cursor.fetchall()
                elif fetch is None:
                    conn.commit()
                    return cursor.rowcount
        else:
            cursor = conn.cursor()
            cursor.execute(query, params or [])
            if fetch == 'one':
                result = cursor.fetchone()
                conn.close()
                return result
            elif fetch == 'all':
                result = cursor.fetchall()
                conn.close()
                return result
            elif fetch is None:
                conn.commit()
                rowcount = cursor.rowcount
                conn.close()
                return rowcount
    except Exception as e:
        if conn:
            conn.rollback() if USE_POSTGRESQL else None
            conn.close()
        raise e

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
                random.randint(3, 8),   # ph_satisfactory
                random.randint(0, 2),   # ph_non_satisfactory
                'Sample inspection data',  # remarks
                '',  # facility_type
                ''   # water_source_type
            ))

    cursor.executemany('''
        INSERT INTO inspection_submissions
        (supply_id, inspector_id, sampling_point_id, submission_date, visits,
         chlorine_total, chlorine_positive, chlorine_negative, chlorine_positive_range,
         chlorine_negative_range, bacteriological_positive, bacteriological_negative,
         bacteriological_pending, isolated_organism, ph_satisfactory, ph_non_satisfactory,
         remarks, facility_type, water_source_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', sample_data)

    conn.commit()
    conn.close()
    print('Sample data added for chart testing')

# Routes
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Route based on user role and parish
    user_role = session.get('role')
    user_parish = session.get('parish', 'Westmoreland')

    # All admins go to the same admin dashboard regardless of parish
    if user_role == 'admin':
        return render_template('admin.html')

    # Inspectors go to their parish-specific dashboard
    elif user_role == 'inspector':
        if user_parish == 'Trelawny':
            return render_template('trelawny.html')
        elif user_parish == 'Hanover':
            return render_template('hanover.html')
        elif user_parish == 'St. James':
            return render_template('st_james.html')
        elif user_parish == 'Westmoreland':
            return render_template('westmoreland.html')
        else:
            # Fallback for unsupported parishes
            return redirect(url_for('login'))

    # Fallback for unknown roles
    return redirect(url_for('login'))

@app.route('/inspector')
def inspector():
    if 'user_id' not in session or session['role'] != 'inspector':
        return redirect(url_for('login'))
    # Route to parish-specific dashboard based on user's parish
    user_parish = session.get('parish', 'Westmoreland')
    if user_parish == 'Trelawny':
        return render_template('trelawny.html')
    elif user_parish == 'Hanover':
        return render_template('hanover.html')
    elif user_parish == 'St. James':
        return render_template('st_james.html')
    else:
        return render_template('westmoreland.html')

@app.route('/admin')
def admin():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    return render_template('admin.html')

@app.route('/trelawny')
def trelawny():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Only allow Trelawny inspectors or any admin to access this dashboard
    user_parish = session.get('parish', 'Westmoreland')
    user_role = session.get('role')

    if user_role != 'admin' and user_parish != 'Trelawny':
        return redirect(url_for('index'))

    return render_template('trelawny.html')

@app.route('/hanover')
def hanover():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Only allow Hanover inspectors or any admin to access this dashboard
    user_parish = session.get('parish', 'Westmoreland')
    user_role = session.get('role')

    if user_role != 'admin' and user_parish != 'Hanover':
        return redirect(url_for('index'))

    return render_template('hanover.html')

@app.route('/westmoreland')
def westmoreland():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Only allow Westmoreland inspectors or any admin to access this dashboard
    user_parish = session.get('parish', 'Westmoreland')
    user_role = session.get('role')

    if user_role != 'admin' and user_parish != 'Westmoreland':
        return redirect(url_for('index'))

    return render_template('westmoreland.html')

@app.route('/st_james')
def st_james():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Only allow St. James inspectors or any admin to access this dashboard
    user_parish = session.get('parish', 'Westmoreland')
    user_role = session.get('role')

    if user_role != 'admin' and user_parish != 'St. James':
        return redirect(url_for('index'))

    return render_template('st_james.html')

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
            supported_parishes = ['Westmoreland', 'Trelawny', 'Hanover', 'St. James']
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
                    // Redirect to index route which will automatically route to correct dashboard
                    window.location.href = '/';
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
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()

    # Get the user's parish
    user = conn.execute('SELECT parish FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if not user:
        conn.close()
        return jsonify({'error': 'User not found'}), 404

    user_parish = user['parish']

    # Filter supplies by parish
    supplies = conn.execute(
        'SELECT * FROM water_supplies WHERE parish = ? ORDER BY type, name',
        (user_parish,)
    ).fetchall()
    conn.close()
    return jsonify([dict(supply) for supply in supplies])

@app.route('/api/sampling-points/<int:supply_id>')
def get_sampling_points(supply_id):
    try:
        conn = get_db_connection()

        # Ensure sampling_points table exists (for Render free tier)
        try:
            if USE_POSTGRESQL:
                cursor = conn.cursor()
                # Test if table exists
                cursor.execute("SELECT 1 FROM sampling_points LIMIT 1")
            else:
                conn.execute("SELECT 1 FROM sampling_points LIMIT 1")
        except Exception as table_error:
            print(f"[SAMPLING-POINTS] Table missing, re-initializing database: {table_error}")
            conn.close()
            init_db()
            add_sample_data()
            conn = get_db_connection()

        if USE_POSTGRESQL:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT sp.id, sp.name, sp.location, sp.description, ws.name as supply_name
                FROM sampling_points sp
                JOIN water_supplies ws ON sp.supply_id = ws.id
                WHERE sp.supply_id = %s
                ORDER BY sp.name
            ''', (supply_id,))
            sampling_points = cursor.fetchall()

            # Convert to list of dicts for PostgreSQL
            result = []
            for point in sampling_points:
                result.append({
                    'id': point[0],
                    'name': point[1],
                    'location': point[2],
                    'description': point[3],
                    'supply_name': point[4]
                })
        else:
            sampling_points = conn.execute('''
                SELECT sp.id, sp.name, sp.location, sp.description, ws.name as supply_name
                FROM sampling_points sp
                JOIN water_supplies ws ON sp.supply_id = ws.id
                WHERE sp.supply_id = ?
                ORDER BY sp.name
            ''', (supply_id,)).fetchall()
            result = [dict(point) for point in sampling_points]

        conn.close()
        print(f"[SAMPLING-POINTS] Found {len(result)} sampling points for supply_id {supply_id}")
        return jsonify(result)

    except Exception as e:
        print(f"[SAMPLING-POINTS] Error getting sampling points for supply_id {supply_id}: {e}")
        return jsonify({'error': 'Failed to load sampling points', 'details': str(e)}), 500

@app.route('/api/debug/database-status')
def debug_database_status():
    """Debug endpoint to check database status - especially useful for Render free tier"""
    try:
        conn = get_db_connection()
        status = {'database_connected': True, 'tables': {}, 'errors': []}

        # Check each table
        tables_to_check = ['water_supplies', 'sampling_points', 'users', 'inspection_submissions']

        for table_name in tables_to_check:
            try:
                if USE_POSTGRESQL:
                    cursor = conn.cursor()
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    count = cursor.fetchone()[0]
                else:
                    count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                status['tables'][table_name] = {'exists': True, 'count': count}
            except Exception as table_error:
                status['tables'][table_name] = {'exists': False, 'error': str(table_error)}
                status['errors'].append(f"{table_name}: {table_error}")

        # Check specific Trelawny data
        try:
            if USE_POSTGRESQL:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM water_supplies WHERE parish = %s", ('Trelawny',))
                trelawny_supplies = cursor.fetchone()[0]
                cursor.execute('''
                    SELECT COUNT(*)
                    FROM sampling_points sp
                    JOIN water_supplies ws ON sp.supply_id = ws.id
                    WHERE ws.parish = %s
                ''', ('Trelawny',))
                trelawny_points = cursor.fetchone()[0]
            else:
                trelawny_supplies = conn.execute("SELECT COUNT(*) FROM water_supplies WHERE parish = ?", ('Trelawny',)).fetchone()[0]
                trelawny_points = conn.execute('''
                    SELECT COUNT(*)
                    FROM sampling_points sp
                    JOIN water_supplies ws ON sp.supply_id = ws.id
                    WHERE ws.parish = ?
                ''', ('Trelawny',)).fetchone()[0]

            status['trelawny'] = {
                'supplies': trelawny_supplies,
                'sampling_points': trelawny_points
            }
        except Exception as trelawny_error:
            status['trelawny'] = {'error': str(trelawny_error)}
            status['errors'].append(f"Trelawny check: {trelawny_error}")

        conn.close()
        status['environment'] = {
            'use_postgresql': USE_POSTGRESQL,
            'database_path': DATABASE if not USE_POSTGRESQL else 'PostgreSQL'
        }

        return jsonify(status)

    except Exception as e:
        return jsonify({
            'database_connected': False,
            'error': str(e),
            'environment': {
                'use_postgresql': USE_POSTGRESQL,
                'database_path': DATABASE if not USE_POSTGRESQL else 'PostgreSQL'
            }
        }), 500

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
                'labels': ['Positive', 'Negative', 'Result Pending'],
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

    try:
        # Determine bacteriological status
        # Status is 'pending' if: there are pending samples OR all values are 0 (no results entered yet)
        # Status is 'complete' only if: there are results (positive or negative > 0) and no pending samples
        bacteriological_positive = data.get('bacteriological_positive', 0)
        bacteriological_negative = data.get('bacteriological_negative', 0)
        bacteriological_pending = data.get('bacteriological_pending', 0)
        bacteriological_results_entered = bacteriological_positive + bacteriological_negative

        bacteriological_status = 'pending' if (bacteriological_pending > 0 or bacteriological_results_entered == 0) else 'complete'

        # Prepare the insertion based on database type
        if USE_POSTGRESQL:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO inspection_submissions
                (supply_id, inspector_id, sampling_point_id, submission_date, visits, chlorine_total, chlorine_positive,
                 chlorine_negative, chlorine_positive_range, chlorine_negative_range, bacteriological_positive,
                 bacteriological_negative, bacteriological_pending, bacteriological_rejected, bacteriological_broken,
                 bacteriological_rejected_reason, bacteriological_broken_reason, bacteriological_status,
                 bacteriological_positive_status, bacteriological_negative_status,
                 isolated_organism, ph_satisfactory, ph_non_satisfactory, ph_non_satisfactory_params,
                 chemical_satisfactory, chemical_non_satisfactory, chemical_non_satisfactory_params,
                 turbidity_satisfactory, turbidity_non_satisfactory,
                 temperature_satisfactory, temperature_non_satisfactory,
                 remarks, facility_type, water_source_type)
                VALUES (%s, %s, %s, CURRENT_DATE, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                data['supply_id'], session['user_id'], data.get('sampling_point_id'),
                data.get('visits', 0), data.get('chlorine_total', 0), data.get('chlorine_positive', 0),
                data.get('chlorine_negative', 0), data.get('chlorine_positive_range', ''),
                data.get('chlorine_negative_range', ''), data.get('bacteriological_positive', 0),
                data.get('bacteriological_negative', 0), data.get('bacteriological_pending', 0),
                data.get('bacteriological_rejected', 0), data.get('bacteriological_broken', 0),
                data.get('bacteriological_rejected_reason', ''), data.get('bacteriological_broken_reason', ''),
                bacteriological_status,
                data.get('bacteriological_positive_status', ''), data.get('bacteriological_negative_status', ''),
                data.get('isolated_organism', ''), data.get('ph_satisfactory', 0),
                data.get('ph_non_satisfactory', 0), json.dumps(data.get('ph_non_satisfactory_params', [])),
                data.get('chemical_satisfactory', 0), data.get('chemical_non_satisfactory', 0),
                json.dumps(data.get('chemical_non_satisfactory_params', [])),
                data.get('turbidity_satisfactory', 0), data.get('turbidity_non_satisfactory', 0),
                data.get('temperature_satisfactory', 0), data.get('temperature_non_satisfactory', 0),
                data.get('remarks', ''), data.get('facility_type', ''), data.get('water_source_type', '')
            ))
            submission_id = cursor.fetchone()[0]

            # Add inspector signature
            cursor.execute('''
                INSERT INTO inspector_signatures (submission_id, inspector_id, action_type, notes)
                VALUES (%s, %s, %s, %s)
            ''', (submission_id, session['user_id'], 'Initial Submission', 'Created inspection report'))

            # Get the submission with supply info
            cursor.execute('''
                SELECT s.*, ws.name as supply_name, ws.type, ws.agency,
                       u.full_name as inspector_name
                FROM inspection_submissions s
                JOIN water_supplies ws ON s.supply_id = ws.id
                JOIN users u ON s.inspector_id = u.id
                WHERE s.id = %s
            ''', (submission_id,))
            submission_data = cursor.fetchone()

        else:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO inspection_submissions
                (supply_id, inspector_id, sampling_point_id, submission_date, visits, chlorine_total, chlorine_positive,
                 chlorine_negative, chlorine_positive_range, chlorine_negative_range, bacteriological_positive,
                 bacteriological_negative, bacteriological_pending, bacteriological_rejected, bacteriological_broken,
                 bacteriological_rejected_reason, bacteriological_broken_reason, bacteriological_status,
                 bacteriological_positive_status, bacteriological_negative_status,
                 isolated_organism, ph_satisfactory, ph_non_satisfactory, ph_non_satisfactory_params,
                 chemical_satisfactory, chemical_non_satisfactory, chemical_non_satisfactory_params,
                 turbidity_satisfactory, turbidity_non_satisfactory,
                 temperature_satisfactory, temperature_non_satisfactory,
                 remarks, facility_type, water_source_type)
                VALUES (?, ?, ?, date('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['supply_id'], session['user_id'], data.get('sampling_point_id'),
                data.get('visits', 0), data.get('chlorine_total', 0), data.get('chlorine_positive', 0),
                data.get('chlorine_negative', 0), data.get('chlorine_positive_range', ''),
                data.get('chlorine_negative_range', ''), data.get('bacteriological_positive', 0),
                data.get('bacteriological_negative', 0), data.get('bacteriological_pending', 0),
                data.get('bacteriological_rejected', 0), data.get('bacteriological_broken', 0),
                data.get('bacteriological_rejected_reason', ''), data.get('bacteriological_broken_reason', ''),
                bacteriological_status,
                data.get('bacteriological_positive_status', ''), data.get('bacteriological_negative_status', ''),
                data.get('isolated_organism', ''), data.get('ph_satisfactory', 0),
                data.get('ph_non_satisfactory', 0), json.dumps(data.get('ph_non_satisfactory_params', [])),
                data.get('chemical_satisfactory', 0), data.get('chemical_non_satisfactory', 0),
                json.dumps(data.get('chemical_non_satisfactory_params', [])),
                data.get('turbidity_satisfactory', 0), data.get('turbidity_non_satisfactory', 0),
                data.get('temperature_satisfactory', 0), data.get('temperature_non_satisfactory', 0),
                data.get('remarks', ''), data.get('facility_type', ''), data.get('water_source_type', '')
            ))

            submission_id = cursor.lastrowid

            # Add inspector signature
            cursor.execute('''
                INSERT INTO inspector_signatures (submission_id, inspector_id, action_type, notes)
                VALUES (?, ?, ?, ?)
            ''', (submission_id, session['user_id'], 'Initial Submission', 'Created inspection report'))

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
        print(f"[ERROR] Submission failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/my-submissions')
def get_my_submissions():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    conn = get_db_connection()
    # Changed to show ALL submissions across all parishes, not just current inspector's
    submissions = conn.execute('''
        SELECT s.*, ws.name as supply_name, ws.type, ws.agency, ws.parish,
               sp.name as sampling_point_name, sp.location as sampling_point_location,
               u.full_name as primary_inspector_name
        FROM inspection_submissions s
        JOIN water_supplies ws ON s.supply_id = ws.id
        LEFT JOIN sampling_points sp ON s.sampling_point_id = sp.id
        JOIN users u ON s.inspector_id = u.id
        ORDER BY s.created_at DESC
        LIMIT 50
    ''').fetchall()
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

@app.route('/api/submissions/<int:submission_id>')
def get_submission_details_plural(submission_id):
    """Alternative endpoint with plural 'submissions' for consistency"""
    return get_submission_details(submission_id)

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

@app.route('/api/update-sample/<int:submission_id>', methods=['POST'])
def update_sample_results(submission_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    try:
        data = request.get_json()
        positive_add = int(data.get('bacteriological_positive_add', 0))
        negative_add = int(data.get('bacteriological_negative_add', 0))

        conn = get_db_connection()

        # Get current values
        if USE_POSTGRESQL:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT bacteriological_positive, bacteriological_negative, bacteriological_pending, inspector_id
                FROM inspection_submissions
                WHERE id = %s
            ''', (submission_id,))
            result = cursor.fetchone()
        else:
            result = conn.execute('''
                SELECT bacteriological_positive, bacteriological_negative, bacteriological_pending, inspector_id
                FROM inspection_submissions
                WHERE id = ?
            ''', (submission_id,)).fetchone()

        if not result:
            conn.close()
            return jsonify({'error': 'Submission not found'}), 404

        current_positive = result[0] or 0
        current_negative = result[1] or 0
        current_pending = result[2] or 0
        inspector_id = result[3]

        # Verify the user is the inspector who created this submission
        if inspector_id != session['user_id']:
            conn.close()
            return jsonify({'error': 'Unauthorized - you can only update your own submissions'}), 403

        # Validate that we're not adding more than pending
        if positive_add + negative_add > current_pending:
            conn.close()
            return jsonify({'error': 'Total results exceed pending count'}), 400

        # Calculate new values
        new_positive = current_positive + positive_add
        new_negative = current_negative + negative_add
        new_pending = current_pending - (positive_add + negative_add)

        # Update the database
        if USE_POSTGRESQL:
            cursor.execute('''
                UPDATE inspection_submissions
                SET bacteriological_positive = %s,
                    bacteriological_negative = %s,
                    bacteriological_pending = %s
                WHERE id = %s
            ''', (new_positive, new_negative, new_pending, submission_id))
            conn.commit()
            cursor.close()
        else:
            conn.execute('''
                UPDATE inspection_submissions
                SET bacteriological_positive = ?,
                    bacteriological_negative = ?,
                    bacteriological_pending = ?
                WHERE id = ?
            ''', (new_positive, new_negative, new_pending, submission_id))
            conn.commit()

        conn.close()

        return jsonify({
            'success': True,
            'message': 'Sample results updated successfully',
            'new_values': {
                'bacteriological_positive': new_positive,
                'bacteriological_negative': new_negative,
                'bacteriological_pending': new_pending
            }
        })

    except Exception as e:
        print(f"Error updating sample results: {e}")
        return jsonify({'error': f'Failed to update sample results: {str(e)}'}), 500

@app.route('/api/update-bacteriological', methods=['POST'])
def update_bacteriological():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    try:
        data = request.get_json()
        submission_id = data.get('id')
        new_positive = int(data.get('bacteriological_positive', 0))
        new_negative = int(data.get('bacteriological_negative', 0))
        new_pending = int(data.get('bacteriological_pending', 0))
        organism = data.get('isolated_organism', None)
        bacteriological_status = data.get('bacteriological_status', 'pending')

        conn = get_db_connection()

        # Get current values and verify ownership
        if USE_POSTGRESQL:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT inspector_id
                FROM inspection_submissions
                WHERE id = %s
            ''', (submission_id,))
            result = cursor.fetchone()
        else:
            result = conn.execute('''
                SELECT inspector_id
                FROM inspection_submissions
                WHERE id = ?
            ''', (submission_id,)).fetchone()

        if not result:
            conn.close()
            return jsonify({'error': 'Submission not found'}), 404

        inspector_id = result[0]

        # Verify the user is the inspector who created this submission
        if inspector_id != session['user_id']:
            conn.close()
            return jsonify({'error': 'Unauthorized - you can only update your own submissions'}), 403

        # Update the database
        if USE_POSTGRESQL:
            cursor.execute('''
                UPDATE inspection_submissions
                SET bacteriological_positive = %s,
                    bacteriological_negative = %s,
                    bacteriological_pending = %s,
                    isolated_organism = %s,
                    bacteriological_status = %s
                WHERE id = %s
            ''', (new_positive, new_negative, new_pending, organism, bacteriological_status, submission_id))
            conn.commit()
            cursor.close()
        else:
            conn.execute('''
                UPDATE inspection_submissions
                SET bacteriological_positive = ?,
                    bacteriological_negative = ?,
                    bacteriological_pending = ?,
                    isolated_organism = ?,
                    bacteriological_status = ?
                WHERE id = ?
            ''', (new_positive, new_negative, new_pending, organism, bacteriological_status, submission_id))
            conn.commit()

        conn.close()

        return jsonify({
            'success': True,
            'message': 'Bacteriological results updated successfully',
            'new_values': {
                'bacteriological_positive': new_positive,
                'bacteriological_negative': new_negative,
                'bacteriological_pending': new_pending,
                'isolated_organism': organism,
                'bacteriological_status': bacteriological_status
            }
        })

    except Exception as e:
        print(f"Error updating bacteriological results: {e}")
        return jsonify({'error': f'Failed to update bacteriological results: {str(e)}'}), 500

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
                    <label>Result Pending</label>
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
            LEFT JOIN wasamoter_supplies ws ON t.supply_id = ws.id
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

@app.route('/api/current-user', methods=['GET'])
def get_current_user():
    """Get current logged in user's information"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    conn = get_db_connection()
    user = conn.execute('''
        SELECT id, username, full_name, role, COALESCE(parish, 'Westmoreland') as parish
        FROM users
        WHERE id = ?
    ''', (session['user_id'],)).fetchone()
    conn.close()

    if not user:
        return jsonify({'error': 'User not found'}), 404

    return jsonify(dict(user))

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

@app.route('/api/upload-document', methods=['POST'])
def upload_document():
    """Upload a document to the Tool Kit"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400

    try:
        # Secure the filename
        filename = secure_filename(file.filename)

        # Create the upload directory if it doesn't exist
        upload_dir = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])
        os.makedirs(upload_dir, exist_ok=True)

        # Save the file
        filepath = os.path.join(upload_dir, filename)
        file.save(filepath)

        # Store document info in database (we'll create this table next)
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO documents (filename, original_name, file_path, uploaded_by, upload_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (filename, file.filename, filepath, session['user_id'], datetime.now()))
            conn.commit()
            document_id = cursor.lastrowid
        finally:
            conn.close()

        return jsonify({
            'success': True,
            'message': 'Document uploaded successfully',
            'document_id': document_id,
            'filename': filename
        }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/documents', methods=['GET'])
def get_documents():
    """Get list of available documents"""
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        documents = cursor.execute('''
            SELECT id, filename, original_name, upload_date,
                   (SELECT full_name FROM users WHERE id = documents.uploaded_by) as uploaded_by_name
            FROM documents
            ORDER BY upload_date DESC
        ''').fetchall()
        conn.close()

        return jsonify([dict(doc) for doc in documents])
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/documents/<int:doc_id>/download')
def download_document(doc_id):
    """Download a specific document"""
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        doc = cursor.execute('''
            SELECT filename, original_name, file_path
            FROM documents
            WHERE id = ?
        ''', (doc_id,)).fetchone()
        conn.close()

        if not doc:
            return jsonify({'error': 'Document not found'}), 404

        return send_file(doc['file_path'], as_attachment=True, download_name=doc['original_name'])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/documents/<int:doc_id>', methods=['DELETE'])
def delete_document(doc_id):
    """Delete a specific document (admin only)"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Get document info before deletion
        doc = cursor.execute('''
            SELECT filename, file_path
            FROM documents
            WHERE id = ?
        ''', (doc_id,)).fetchone()

        if not doc:
            conn.close()
            return jsonify({'error': 'Document not found'}), 404

        # Delete from database
        cursor.execute('DELETE FROM documents WHERE id = ?', (doc_id,))
        conn.commit()
        conn.close()

        # Delete physical file
        try:
            if os.path.exists(doc['file_path']):
                os.remove(doc['file_path'])
        except OSError:
            pass  # Continue even if file deletion fails

        return jsonify({'success': True, 'message': 'Document deleted successfully'})

    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/upload')
def upload_page():
    """Temporary upload page for documents"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    return render_template('upload.html')

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

def migrate_database():
    """Add missing columns to existing databases"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check if pH columns exist, add them if they don't
        if USE_POSTGRESQL:
            # PostgreSQL migration
            cursor.execute('''
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'inspection_submissions' AND column_name = 'ph_satisfactory'
            ''')
            if not cursor.fetchone():
                print("Adding missing pH columns to PostgreSQL database...")
                cursor.execute('ALTER TABLE inspection_submissions ADD COLUMN ph_satisfactory INTEGER DEFAULT 0')
                cursor.execute('ALTER TABLE inspection_submissions ADD COLUMN ph_non_satisfactory INTEGER DEFAULT 0')
                cursor.execute('ALTER TABLE inspection_submissions ADD COLUMN ph_non_satisfactory_range VARCHAR(50)')

            # Check for water_source_type column
            cursor.execute('''
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'inspection_submissions' AND column_name = 'water_source_type'
            ''')
            if not cursor.fetchone():
                print("Adding water_source_type column to PostgreSQL database...")
                cursor.execute('ALTER TABLE inspection_submissions ADD COLUMN water_source_type VARCHAR(100)')
        else:
            # SQLite migration
            cursor.execute('PRAGMA table_info(inspection_submissions)')
            columns = [column[1] for column in cursor.fetchall()]

            if 'ph_satisfactory' not in columns:
                print("Adding missing pH columns to SQLite database...")
                cursor.execute('ALTER TABLE inspection_submissions ADD COLUMN ph_satisfactory INTEGER DEFAULT 0')
                cursor.execute('ALTER TABLE inspection_submissions ADD COLUMN ph_non_satisfactory INTEGER DEFAULT 0')
                cursor.execute('ALTER TABLE inspection_submissions ADD COLUMN ph_non_satisfactory_range TEXT')

            if 'water_source_type' not in columns:
                print("Adding water_source_type column to SQLite database...")
                cursor.execute('ALTER TABLE inspection_submissions ADD COLUMN water_source_type TEXT')

        conn.commit()
        print("Database migration completed successfully")
    except Exception as e:
        print(f"Migration error: {e}")
        conn.rollback()
    finally:
        conn.close()

def migrate_bacteriological_columns():
    """Add bacteriological_rejected, bacteriological_broken, and bacteriological_status columns"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        if USE_POSTGRESQL:
            # Check if columns exist
            cursor.execute('''
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'inspection_submissions' AND column_name = 'bacteriological_rejected'
            ''')
            if not cursor.fetchone():
                print("Adding bacteriological rejected/broken columns to PostgreSQL database...")
                cursor.execute('ALTER TABLE inspection_submissions ADD COLUMN bacteriological_rejected INTEGER DEFAULT 0')
                cursor.execute('ALTER TABLE inspection_submissions ADD COLUMN bacteriological_broken INTEGER DEFAULT 0')
                cursor.execute('ALTER TABLE inspection_submissions ADD COLUMN bacteriological_rejected_reason TEXT')
                cursor.execute('ALTER TABLE inspection_submissions ADD COLUMN bacteriological_broken_reason TEXT')

            # Check for bacteriological_status column
            cursor.execute('''
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'inspection_submissions' AND column_name = 'bacteriological_status'
            ''')
            if not cursor.fetchone():
                print("Adding bacteriological_status column to PostgreSQL database...")
                cursor.execute("ALTER TABLE inspection_submissions ADD COLUMN bacteriological_status VARCHAR(20) DEFAULT 'pending'")
        else:
            # SQLite migration
            cursor.execute('PRAGMA table_info(inspection_submissions)')
            columns = [column[1] for column in cursor.fetchall()]

            if 'bacteriological_rejected' not in columns:
                print("Adding bacteriological rejected/broken columns to SQLite database...")
                cursor.execute('ALTER TABLE inspection_submissions ADD COLUMN bacteriological_rejected INTEGER DEFAULT 0')
                cursor.execute('ALTER TABLE inspection_submissions ADD COLUMN bacteriological_broken INTEGER DEFAULT 0')
                cursor.execute('ALTER TABLE inspection_submissions ADD COLUMN bacteriological_rejected_reason TEXT')
                cursor.execute('ALTER TABLE inspection_submissions ADD COLUMN bacteriological_broken_reason TEXT')

            if 'bacteriological_status' not in columns:
                print("Adding bacteriological_status column to SQLite database...")
                cursor.execute("ALTER TABLE inspection_submissions ADD COLUMN bacteriological_status TEXT DEFAULT 'pending'")

        conn.commit()
        print("Bacteriological columns migration completed successfully")
    except Exception as e:
        print(f"Bacteriological migration error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5004))
    debug = os.environ.get('FLASK_ENV', 'development') == 'development'

    # Run database migration first
    migrate_database()
    migrate_bacteriological_columns()

    # Add sample data for testing
    add_sample_data()

    if debug:
        # Development mode
        socketio.run(app, host='0.0.0.0', port=port, debug=True, allow_unsafe_werkzeug=True)
    else:
        # Production mode - but allow unsafe werkzeug for local testing and Render deployment
        socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)