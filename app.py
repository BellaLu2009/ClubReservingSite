import sqlite3
import datetime
import json
from flask import Flask, jsonify, request, g, render_template
from flask_cors import CORS
import os
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user

# --- App & DB Setup ---
app = Flask(__name__)
app.secret_key = 'your-super-secret-key-change-me'
CORS(app, supports_credentials=True)
DATABASE = 'club_booking.db'
UPLOAD_FOLDER = 'static/avatars'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Flask-Login Setup ---
login_manager = LoginManager()
login_manager.init_app(app)

class User(UserMixin):
    def __init__(self, user_id, username, name, roles):
        self.id = user_id
        self.username = username
        self.name = name
        self.roles = roles

@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    user_row = db.execute('SELECT user_id, username, name, roles FROM users WHERE user_id = ?', (user_id,)).fetchone()
    if not user_row:
        return None
    roles = json.loads(user_row['roles']) if user_row['roles'] else []
    return User(user_id=user_row['user_id'], username=user_row['username'], name=user_row['name'], roles=roles)

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE, check_same_thread=False)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(_):
    if hasattr(g, 'db'):
        g.db.close()

def init_db():
    if os.path.exists(DATABASE):
        return
    with sqlite3.connect(DATABASE) as db:
        cursor = db.cursor()
        # ... (table creation as before) ...
        db.commit()

def to_dict(row):
    return dict(row) if row else None

def is_admin():
    return current_user.is_authenticated and 'ADMIN' in current_user.roles

@app.route('/')
def index():
    return render_template('社团预约.html')

@app.route('/admin')
@login_required
def admin_panel():
    if not is_admin():
        return "Access Denied: You do not have administrator privileges.", 403
    return render_template('admin.html')

# --- Admin APIs ---
@app.route('/api/admin/users', methods=['GET'])
@login_required
def admin_get_users():
    if not is_admin(): return jsonify({"error": "Unauthorized"}), 403
    db = get_db()
    users = db.execute('SELECT user_id, username, name, class_name, student_id, roles FROM users').fetchall()
    return jsonify([to_dict(u) for u in users])

@app.route('/api/admin/user/<user_id>', methods=['PUT', 'DELETE'])
@login_required
def admin_manage_user(user_id):
    if not is_admin(): return jsonify({"error": "Unauthorized"}), 403
    db = get_db()
    if request.method == 'DELETE':
        db.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
        db.commit()
        return jsonify({"message": "User deleted successfully."})
    if request.method == 'PUT':
        data = request.json
        roles = data.get('roles')
        if roles is not None:
            roles_json = json.dumps(roles)
            db.execute('UPDATE users SET roles = ? WHERE user_id = ?', (roles_json, user_id))
            db.commit()
            return jsonify({"message": "User roles updated."})
        return jsonify({"error": "No roles provided"}), 400

@app.route('/api/admin/clubs', methods=['POST'])
@login_required
def admin_create_club():
    if not is_admin(): return jsonify({"error": "Unauthorized"}), 403
    data = request.json
    club_id = 'c_' + str(int(datetime.datetime.now().timestamp()))
    db = get_db()
    db.execute(
        'INSERT INTO clubs (club_id, name, category, description, leader_id, location, max_capacity, day_of_week, start_time, end_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (club_id, data['name'], data['category'], data['description'], data['leader_id'], data['location'], data['max_capacity'], data['day_of_week'], data['start_time'], data['end_time'])
    )
    db.commit()
    return jsonify({"message": "Club created", "club_id": club_id}), 201

@app.route('/api/admin/club/<club_id>', methods=['PUT', 'DELETE'])
@login_required
def admin_manage_club(club_id):
    if not is_admin(): return jsonify({"error": "Unauthorized"}), 403
    db = get_db()
    if request.method == 'DELETE':
        # Also delete associated reservations to maintain integrity
        db.execute('DELETE FROM reservations WHERE club_id = ?', (club_id,))
        db.execute('DELETE FROM clubs WHERE club_id = ?', (club_id,))
        db.commit()
        return jsonify({"message": "Club deleted successfully."})
    if request.method == 'PUT':
        data = request.json
        db.execute(
            'UPDATE clubs SET name=?, category=?, description=?, leader_id=?, location=?, max_capacity=?, day_of_week=?, start_time=?, end_time=? WHERE club_id=?',
            (data['name'], data['category'], data['description'], data['leader_id'], data['location'], data['max_capacity'], data['day_of_week'], data['start_time'], data['end_time'], club_id)
        )
        db.commit()
        return jsonify({"message": "Club updated."})

# --- Public & User APIs ---
@app.route('/api/register', methods=['POST'])
def register():
    # ... (code as before) ...
    pass

@app.route('/api/login', methods=['POST'])
def login():
    # ... (code as before) ...
    pass

@app.route('/api/logout', methods=['POST'])
@login_required
def logout():
    # ... (code as before) ...
    pass

@app.route('/api/session')
def get_session():
    # ... (code as before) ...
    pass

@app.route('/api/user/profile', methods=['PUT'])
@login_required
def update_profile():
    # ... (code as before) ...
    pass

@app.route('/api/user/password', methods=['PUT'])
@login_required
def update_password():
    # ... (code as before) ...
    pass

@app.route('/api/clubs')
def get_clubs():
    query = "SELECT c.*, (SELECT COUNT(*) FROM reservations r WHERE r.club_id = c.club_id AND r.status = 'ACTIVE') as current_capacity, (SELECT COUNT(*) FROM reservations r WHERE r.club_id = c.club_id AND r.status = 'WAITLISTED') as waitlist_count FROM clubs c;"
    clubs = get_db().execute(query).fetchall()
    return jsonify([to_dict(club) for club in clubs])

# ... (rest of the API endpoints as before) ...

if __name__ == '__main__':
    # Create upload folder if it doesn't exist
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    init_db()
    app.run(host='0.0.0.0', debug=True, port=5001)