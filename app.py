import sqlite3
import datetime
import json
from flask import Flask, jsonify, request, g, render_template
from flask_cors import CORS
import os
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import random
import string

# --- App & DB Setup ---
app = Flask(__name__)
app.secret_key = 'your-super-secret-key-change-me'
CORS(app, supports_credentials=True)
DATABASE = 'club_booking.db'
AVATAR_UPLOAD_FOLDER = 'static/avatars'
CLUB_PHOTOS_UPLOAD_FOLDER = 'static/club_photos'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['AVATAR_UPLOAD_FOLDER'] = AVATAR_UPLOAD_FOLDER
app.config['CLUB_PHOTOS_UPLOAD_FOLDER'] = CLUB_PHOTOS_UPLOAD_FOLDER

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
    # CRITICAL FIX: Only create the DB if it doesn't exist.
    if os.path.exists(DATABASE):
        return
        
    with sqlite3.connect(DATABASE) as db:
        cursor = db.cursor()
        cursor.execute('''
        CREATE TABLE users (
            user_id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
            name TEXT NOT NULL, class_name TEXT, student_id TEXT, avatar_url TEXT, roles TEXT
        );''')
        cursor.execute('''
        CREATE TABLE clubs (
            club_id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT, description TEXT,
            leader_id TEXT, location TEXT, max_capacity INTEGER, day_of_week INTEGER,
            start_time TEXT, end_time TEXT, FOREIGN KEY (leader_id) REFERENCES users(user_id)
        );''')
        cursor.execute('''
        CREATE TABLE reservations (
            reservation_id TEXT PRIMARY KEY, user_id TEXT, club_id TEXT, status TEXT,
            created_at TEXT, FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (club_id) REFERENCES clubs(club_id)
        );''')
        cursor.execute('''
        CREATE TABLE notifications (
            notification_id TEXT PRIMARY KEY, club_id TEXT, title TEXT, content TEXT,
            created_at TEXT, FOREIGN KEY (club_id) REFERENCES clubs(club_id)
        );''')
        cursor.execute('''
        CREATE TABLE club_photos (
            photo_id TEXT PRIMARY KEY,
            club_id TEXT,
            photo_url TEXT NOT NULL,
            caption TEXT,
            uploaded_at TEXT,
            FOREIGN KEY (club_id) REFERENCES clubs(club_id)
        );''')
        cursor.execute('''
        CREATE TABLE club_events (
            event_id TEXT PRIMARY KEY,
            club_id TEXT,
            check_in_code TEXT NOT NULL,
            created_at TEXT,
            expires_at TEXT,
            FOREIGN KEY (club_id) REFERENCES clubs(club_id)
        );''')
        cursor.execute('''
        CREATE TABLE event_attendance (
            attendance_id TEXT PRIMARY KEY,
            event_id TEXT,
            user_id TEXT,
            checked_in_at TEXT,
            FOREIGN KEY (event_id) REFERENCES club_events(event_id),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );''')
        
        admin_pass = generate_password_hash('admin')
        user_pass = generate_password_hash('123456')
        # The true Administrator with the 'ADMIN' role
        cursor.execute('INSERT INTO users VALUES (?,?,?,?,?,?,?,?)', ('admin_01', 'admin', admin_pass, '管理员', 'N/A', 'N/A', 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=120', '["ADMIN", "STUDENT", "CLUB_LEADER"]'))
        # A regular student user
        cursor.execute('INSERT INTO users VALUES (?,?,?,?,?,?,?,?)', ('user_01', 'zhangsan', user_pass, '张三', '高二(3)班', '2026020315', 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=120', '["STUDENT"]'))
        
        clubs_data = [
            ("c_1", "机器人实验室", "ACADEMIC", "探索 VEX 机器人工程架构...", "admin_01", "综合楼402", 1, 2, "16:00:00", "17:30:00"),
            ("c_2", "潮流篮球社", "SPORTS", "高强度全场战术配合...", None, "室内体育馆A厅", 30, 4, "16:00:00", "17:30:00"),
            ("c_3", "青年志愿者协会", "PUBLIC_WELFARE", "参与社区服务和公益活动...", None, "学生活动中心", 40, 1, "17:30:00", "19:00:00"),
        ]
        cursor.executemany('INSERT INTO clubs VALUES (?,?,?,?,?,?,?,?,?,?)', clubs_data)
        db.commit()

def to_dict(row):
    return dict(row) if row else None

def is_admin():
    return current_user.is_authenticated and 'ADMIN' in current_user.roles

def is_club_leader():
    return current_user.is_authenticated and 'CLUB_LEADER' in current_user.roles

def generate_check_in_code(length=6):
    """Generate a random alphanumeric check-in code."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

@app.route('/')
def index():
    return render_template('社团预约.html')

@app.route('/admin')
@login_required
def admin_panel():
    if not is_admin():
        return "Access Denied: You do not have administrator privileges.", 403
    return render_template('admin.html')

@app.route('/leader')
@login_required
def leader_panel():
    if not is_club_leader():
        return "Access Denied: You do not have club leader privileges.", 403
    return render_template('leader.html')

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

@app.route('/api/unclaimed-clubs', methods=['GET'])
def get_unclaimed_clubs():
    db = get_db()
    clubs = db.execute("SELECT club_id, name FROM clubs WHERE leader_id IS NULL OR leader_id = ''").fetchall()
    return jsonify([to_dict(c) for c in clubs])

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username, password, name = data.get('username'), data.get('password'), data.get('name')
    is_leader = data.get('isLeader', False)
    club_id = data.get('clubId')

    if not all([username, password, name]):
        return jsonify({"error": "缺少必要信息"}), 400
    
    db = get_db()
    if db.execute('SELECT user_id FROM users WHERE username = ?', (username,)).fetchone():
        return jsonify({"error": "用户名已存在"}), 409

    user_id = 'u_' + str(int(datetime.datetime.now().timestamp()))
    password_hash = generate_password_hash(password)
    
    user_roles = ['STUDENT']
    if is_leader:
        if not club_id:
            return jsonify({"error": "作为社长注册必须选择一个社团"}), 400
        # Verify the selected club is actually unclaimed
        club = db.execute("SELECT leader_id FROM clubs WHERE club_id = ?", (club_id,)).fetchone()
        if not club or (club['leader_id'] is not None and club['leader_id'] != ''):
            return jsonify({"error": "所选社团已被认领或不存在"}), 409
        user_roles.append('CLUB_LEADER')

    roles_json = json.dumps(user_roles)
    avatar = f'https://i.pravatar.cc/150?u={user_id}'
    
    try:
        db.execute('INSERT INTO users (user_id, username, password_hash, name, roles, avatar_url) VALUES (?, ?, ?, ?, ?, ?)',
                   (user_id, username, password_hash, name, roles_json, avatar))
        
        if is_leader:
            db.execute('UPDATE clubs SET leader_id = ? WHERE club_id = ?', (user_id, club_id))
        
        db.commit()
    except db.Error as e:
        db.rollback()
        return jsonify({"error": f"数据库错误: {e}"}), 500

    return jsonify({"message": "注册成功！"}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username, password = data.get('username'), data.get('password')
    db = get_db()
    user_row = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    if user_row and check_password_hash(user_row['password_hash'], password):
        user = load_user(user_row['user_id'])
        login_user(user)
        user_dict = to_dict(user_row)
        user_dict['roles'] = json.loads(user_dict['roles'])
        return jsonify(user_dict)
    return jsonify({"error": "用户名或密码错误"}), 401

@app.route('/api/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return jsonify({"message": "已成功退出登录"})

@app.route('/api/session')
def get_session():
    if not current_user.is_authenticated:
        return jsonify(None)
    user_row = get_db().execute('SELECT * FROM users WHERE user_id = ?', (current_user.id,)).fetchone()
    user_dict = to_dict(user_row)
    user_dict['roles'] = json.loads(user_dict['roles'])
    return jsonify(user_dict)

@app.route('/api/user/profile', methods=['PUT'])
@login_required
def update_profile():
    db = get_db()
    
    new_username = request.form.get('username')
    if new_username and new_username != current_user.username:
        if db.execute('SELECT user_id FROM users WHERE username = ?', (new_username,)).fetchone():
            return jsonify({"error": "用户名已存在"}), 409
        db.execute('UPDATE users SET username = ? WHERE user_id = ?', (new_username, current_user.id))

    if 'avatar' in request.files:
        file = request.files['avatar']
        if file and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            extension = filename.rsplit('.', 1)[1].lower()
            unique_filename = f"{current_user.id}_{int(datetime.datetime.now().timestamp())}.{extension}"
            
            os.makedirs(app.config['AVATAR_UPLOAD_FOLDER'], exist_ok=True)
            
            path = os.path.join(app.config['AVATAR_UPLOAD_FOLDER'], unique_filename)
            file.save(path)
            
            avatar_url = f"/{path}"
            db.execute('UPDATE users SET avatar_url = ? WHERE user_id = ?', (avatar_url, current_user.id))

    db.commit()
    
    updated_user = db.execute('SELECT * FROM users WHERE user_id = ?', (current_user.id,)).fetchone()
    user_dict = to_dict(updated_user)
    user_dict['roles'] = json.loads(user_dict['roles'])
    return jsonify(user_dict)


@app.route('/api/user/password', methods=['PUT'])
@login_required
def update_password():
    data = request.json
    old_password = data.get('old_password')
    new_password = data.get('new_password')
    student_id_verify = data.get('student_id_verify')
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE user_id = ?', (current_user.id,)).fetchone()

    if not user:
        return jsonify({"error": "用户不存在"}), 404

    if old_password:
        if not check_password_hash(user['password_hash'], old_password):
            return jsonify({"error": "旧密码不正确"}), 400
    elif student_id_verify:
        if user['student_id'] != student_id_verify:
            return jsonify({"error": "身份验证失败，学号不匹配"}), 403
    else:
        return jsonify({"error": "缺少认证信息"}), 400

    new_password_hash = generate_password_hash(new_password)
    db.execute('UPDATE users SET password_hash = ? WHERE user_id = ?', (new_password_hash, current_user.id))
    db.commit()
    return jsonify({"message": "密码更新成功！"})

@app.route('/api/clubs')
def get_clubs():
    query = "SELECT c.*, (SELECT COUNT(*) FROM reservations r WHERE r.club_id = c.club_id AND r.status = 'ACTIVE') as current_capacity, (SELECT COUNT(*) FROM reservations r WHERE r.club_id = c.club_id AND r.status = 'WAITLISTED') as waitlist_count FROM clubs c;"
    clubs = get_db().execute(query).fetchall()
    return jsonify([to_dict(club) for club in clubs])

@app.route('/api/reservations')
@login_required
def get_user_reservations():
    reservations = get_db().execute('SELECT * FROM reservations WHERE user_id = ?', (current_user.id,)).fetchall()
    return jsonify([to_dict(r) for r in reservations])

@app.route('/api/reserve', methods=['POST'])
@login_required
def reserve_club():
    data = request.json
    club_id = data.get('club_id')
    user_id = current_user.id
    db = get_db()
    target_club = db.execute('SELECT * FROM clubs WHERE club_id = ?', (club_id,)).fetchone()
    if not target_club: return jsonify({"error": "社团不存在"}), 404
    existing_reservation = db.execute('SELECT * FROM reservations WHERE user_id = ? AND club_id = ?', (user_id, club_id)).fetchone()
    if existing_reservation: return jsonify({"error": "您已预约或正在等候此社团"}), 409
    user_reservations = db.execute("SELECT c.name, c.day_of_week, c.start_time, c.end_time FROM reservations r JOIN clubs c ON r.club_id = c.club_id WHERE r.user_id = ? AND r.status = 'ACTIVE'", (user_id,)).fetchall()
    for res in user_reservations:
        if res['day_of_week'] == target_club['day_of_week'] and not (target_club['end_time'] <= res['start_time'] or target_club['start_time'] >= res['end_time']):
            return jsonify({"error": f"该时间段您已有预约：【{res['name']}】"}), 409
    current_capacity = db.execute('SELECT COUNT(*) FROM reservations WHERE club_id = ? AND status = "ACTIVE"', (club_id,)).fetchone()[0]
    status = 'ACTIVE' if current_capacity < target_club['max_capacity'] else 'WAITLISTED'
    new_id = 'r_' + str(int(datetime.datetime.now().timestamp()))
    created_time = datetime.datetime.now().isoformat()
    db.execute('INSERT INTO reservations VALUES (?, ?, ?, ?, ?)', (new_id, user_id, club_id, status, created_time))
    db.commit()
    return jsonify({"status": status, "message": "操作成功"}), 201

@app.route('/api/cancel', methods=['POST'])
@login_required
def cancel_reservation():
    data = request.json
    club_id = data.get('club_id')
    user_id = current_user.id
    db = get_db()
    result = db.execute('DELETE FROM reservations WHERE user_id = ? AND club_id = ?', (user_id, club_id))
    if result.rowcount == 0: return jsonify({"error": "未找到您的预约记录"}), 404
    waitlisted_user = db.execute("SELECT * FROM reservations WHERE club_id = ? AND status = 'WAITLISTED' ORDER BY created_at ASC LIMIT 1", (club_id,)).fetchone()
    if waitlisted_user:
        db.execute("UPDATE reservations SET status = 'ACTIVE' WHERE reservation_id = ?", (waitlisted_user['reservation_id'],))
    db.commit()
    return jsonify({"message": "已成功取消。"})

@app.route('/api/notifications')
@login_required
def get_notifications():
    db = get_db()
    club_ids_rows = db.execute('SELECT DISTINCT club_id FROM reservations WHERE user_id = ? AND status = "ACTIVE"', (current_user.id,)).fetchall()
    if not club_ids_rows: return jsonify([])
    placeholders = ','.join('?' for _ in club_ids_rows)
    notifications = db.execute(f'SELECT * FROM notifications WHERE club_id IN ({placeholders}) ORDER BY created_at DESC', [r['club_id'] for r in club_ids_rows]).fetchall()
    return jsonify([to_dict(n) for n in notifications])

@app.route('/api/leader/reservations')
@login_required
def get_leader_reservations():
    db = get_db()
    leader_club = db.execute('SELECT club_id FROM clubs WHERE leader_id = ?', (current_user.id,)).fetchone()
    if not leader_club: return jsonify([])
    reservations = db.execute("SELECT r.reservation_id, u.student_id, u.name as studentName, u.class_name, r.created_at, r.status FROM reservations r JOIN users u ON r.user_id = u.user_id WHERE r.club_id = ? ORDER BY r.status, r.created_at", (leader_club['club_id'],)).fetchall()
    return jsonify([to_dict(r) for r in reservations])

@app.route('/api/leader/notifications', methods=['POST'])
@login_required
def publish_notice():
    data = request.json
    title, content = data.get('title'), data.get('content')
    db = get_db()
    leader_club = db.execute('SELECT club_id FROM clubs WHERE leader_id = ?', (current_user.id,)).fetchone()
    if not leader_club: return jsonify({"error": "Not a club leader"}), 403
    new_id = 'n_' + str(int(datetime.datetime.now().timestamp()))
    created_time = datetime.datetime.now().isoformat()
    db.execute('INSERT INTO notifications VALUES (?, ?, ?, ?, ?)', (new_id, leader_club['club_id'], title, content, created_time))
    db.commit()
    return jsonify({"notification_id": new_id, "club_id": leader_club['club_id'], "title": title, "content": content, "created_at": created_time}), 201

@app.route('/api/leader/club', methods=['PUT'])
@login_required
def update_leader_club():
    db = get_db()
    # First, verify the user is a club leader and get their club
    leader_club = db.execute('SELECT * FROM clubs WHERE leader_id = ?', (current_user.id,)).fetchone()
    if not leader_club:
        return jsonify({"error": "You are not a leader of any club."}), 403

    data = request.json
    
    # Fields that a leader is allowed to update
    allowed_updates = {
        'description': data.get('description'),
        'category': data.get('category'),
        'location': data.get('location'),
        'max_capacity': data.get('max_capacity'),
        'day_of_week': data.get('day_of_week'),
        'start_time': data.get('start_time'),
        'end_time': data.get('end_time')
    }

    # Filter out any fields that were not provided in the request
    updates = {key: value for key, value in allowed_updates.items() if value is not None}

    if not updates:
        return jsonify({"error": "No update information provided."}), 400

    # Build the dynamic SQL query
    set_clause = ', '.join([f'{key} = ?' for key in updates.keys()])
    values = list(updates.values())
    values.append(leader_club['club_id']) # For the WHERE clause

    query = f"UPDATE clubs SET {set_clause} WHERE club_id = ?"
    
    db.execute(query, values)
    db.commit()

    # Fetch the updated club details to return
    updated_club = db.execute('SELECT * FROM clubs WHERE club_id = ?', (leader_club['club_id'],)).fetchone()

    return jsonify(to_dict(updated_club))

@app.route('/api/leader/club/photo', methods=['POST'])
@login_required
def upload_club_photo():
    db = get_db()
    leader_club = db.execute('SELECT * FROM clubs WHERE leader_id = ?', (current_user.id,)).fetchone()
    if not leader_club:
        return jsonify({"error": "You are not a leader of any club."}), 403

    if 'photo' not in request.files:
        return jsonify({"error": "No photo file provided."}), 400
    
    file = request.files['photo']
    caption = request.form.get('caption', '')

    if file.filename == '':
        return jsonify({"error": "No selected file."}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        extension = filename.rsplit('.', 1)[1].lower()
        
        photo_id = 'p_' + str(int(datetime.datetime.now().timestamp()))
        unique_filename = f"{leader_club['club_id']}_{photo_id}.{extension}"
        
        upload_folder = app.config['CLUB_PHOTOS_UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        
        path = os.path.join(upload_folder, unique_filename)
        file.save(path)
        
        photo_url = f"/{path}"
        uploaded_at = datetime.datetime.now().isoformat()

        db.execute(
            'INSERT INTO club_photos (photo_id, club_id, photo_url, caption, uploaded_at) VALUES (?, ?, ?, ?, ?)',
            (photo_id, leader_club['club_id'], photo_url, caption, uploaded_at)
        )
        db.commit()

        new_photo = db.execute('SELECT * FROM club_photos WHERE photo_id = ?', (photo_id,)).fetchone()
        return jsonify(to_dict(new_photo)), 201

    return jsonify({"error": "File type not allowed."}), 400

@app.route('/api/clubs/<string:club_id>/photos', methods=['GET'])
def get_club_photos(club_id):
    db = get_db()
    photos = db.execute('SELECT * FROM club_photos WHERE club_id = ? ORDER BY uploaded_at DESC', (club_id,)).fetchall()
    return jsonify([to_dict(p) for p in photos])

@app.route('/api/leader/club/event', methods=['POST'])
@login_required
def create_check_in_event():
    db = get_db()
    leader_club = db.execute('SELECT * FROM clubs WHERE leader_id = ?', (current_user.id,)).fetchone()
    if not leader_club:
        return jsonify({"error": "You are not a leader of any club."}), 403

    event_id = 'e_' + str(int(datetime.datetime.now().timestamp()))
    check_in_code = generate_check_in_code()
    created_at = datetime.datetime.now()
    expires_at = created_at + datetime.timedelta(minutes=15)

    db.execute(
        'INSERT INTO club_events (event_id, club_id, check_in_code, created_at, expires_at) VALUES (?, ?, ?, ?, ?)',
        (event_id, leader_club['club_id'], check_in_code, created_at.isoformat(), expires_at.isoformat())
    )
    db.commit()

    new_event = db.execute('SELECT * FROM club_events WHERE event_id = ?', (event_id,)).fetchone()
    return jsonify(to_dict(new_event)), 201

@app.route('/api/club/check-in', methods=['POST'])
@login_required
def check_in():
    data = request.json
    check_in_code = data.get('check_in_code')
    if not check_in_code:
        return jsonify({"error": "Check-in code is required."}), 400

    db = get_db()
    now = datetime.datetime.now()

    event = db.execute(
        'SELECT * FROM club_events WHERE check_in_code = ? AND ? < expires_at',
        (check_in_code, now.isoformat())
    ).fetchone()

    if not event:
        return jsonify({"error": "Invalid or expired check-in code."}), 404

    # Check if user is a member of the club (has an active reservation)
    reservation = db.execute(
        'SELECT * FROM reservations WHERE user_id = ? AND club_id = ? AND status = "ACTIVE"',
        (current_user.id, event['club_id'])
    ).fetchone()
    if not reservation:
        return jsonify({"error": "You are not an active member of this club."}), 403

    # Check if user has already checked in for this event
    existing_attendance = db.execute(
        'SELECT * FROM event_attendance WHERE event_id = ? AND user_id = ?',
        (event['event_id'], current_user.id)
    ).fetchone()
    if existing_attendance:
        return jsonify({"error": "You have already checked in for this event."}), 409

    attendance_id = 'a_' + str(int(datetime.datetime.now().timestamp()))
    db.execute(
        'INSERT INTO event_attendance (attendance_id, event_id, user_id, checked_in_at) VALUES (?, ?, ?, ?)',
        (attendance_id, event['event_id'], current_user.id, now.isoformat())
    )
    db.commit()

    return jsonify({"message": "Check-in successful."}), 200

@app.route('/api/leader/club/event/<string:event_id>/attendance', methods=['GET'])
@login_required
def get_event_attendance(event_id):
    db = get_db()
    leader_club = db.execute('SELECT * FROM clubs WHERE leader_id = ?', (current_user.id,)).fetchone()
    if not leader_club:
        return jsonify({"error": "You are not a leader of any club."}), 403

    # Verify the event belongs to the leader's club
    event = db.execute('SELECT * FROM club_events WHERE event_id = ? AND club_id = ?', (event_id, leader_club['club_id'])).fetchone()
    if not event:
        return jsonify({"error": "Event not found or does not belong to your club."}), 404

    attendance_list = db.execute(
        '''
        SELECT u.name, u.student_id, u.class_name, ea.checked_in_at
        FROM event_attendance ea
        JOIN users u ON ea.user_id = u.user_id
        WHERE ea.event_id = ?
        ORDER BY ea.checked_in_at
        ''',
        (event_id,)
    ).fetchall()

    return jsonify([to_dict(row) for row in attendance_list])


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', debug=True, port=5001)