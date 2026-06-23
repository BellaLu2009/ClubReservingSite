import sqlite3
import datetime
from flask import Flask, jsonify, request, g, render_template
from flask_cors import CORS
import os

# --- App & DB Setup ---
# Use the 'templates' folder for HTML files
app = Flask(__name__)
CORS(app)
DATABASE = 'club_booking.db'

def get_db():
    """Opens a new database connection if there is none yet for the current application context."""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE, check_same_thread=False)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    """Closes the database again at the end of the request."""
    if hasattr(g, 'db'):
        g.db.close()

def init_db():
    """Initializes the database and populates it with initial data."""
    if os.path.exists(DATABASE):
        return

    with sqlite3.connect(DATABASE) as db:
        cursor = db.cursor()
        # Create Tables
        cursor.execute('''
        CREATE TABLE users (
            user_id TEXT PRIMARY KEY, username TEXT NOT NULL, name TEXT NOT NULL,
            class_name TEXT, student_id TEXT, avatar_url TEXT, roles TEXT
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

        # Insert Initial Data
        cursor.execute('INSERT INTO users VALUES (?,?,?,?,?,?,?)', ('u_01', 'zhangsan', '张三', '高二(3)班', '2026020315', 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=120&auto=format&fit=crop&q=80', '["STUDENT", "CLUB_LEADER"]'))
        clubs_data = [
            ("c_1", "机器人实验室", "ACADEMIC", "探索 VEX 机器人工程架构...", "u_01", "综合楼402", 25, 2, "16:00:00", "17:30:00"),
            ("c_2", "潮流篮球社", "SPORTS", "高强度全场战术配合...", "u_other", "室内体育馆A厅", 30, 4, "16:00:00", "17:30:00"),
            ("c_3", "摇滚吉他社", "CRAFT", "从零基础和弦指弹...", "u_other", "艺术楼小剧场", 15, 1, "17:30:00", "19:00:00"),
            ("c_4", "视觉创意美术社", "CRAFT", "涵盖现代素描...", "u_other", "美术画室B", 20, 3, "16:00:00", "17:30:00"),
            ("c_5", "室内羽毛球社", "SPORTS", "提供专业级木地板场地...", "u_other", "羽毛球馆3号场", 20, 2, "16:00:00", "17:30:00")
        ]
        cursor.executemany('INSERT INTO clubs VALUES (?,?,?,?,?,?,?,?,?,?)', clubs_data)
        cursor.execute('INSERT INTO reservations VALUES (?,?,?,?,?)', ('r_init_1', 'u_01', 'c_4', 'ACTIVE', (datetime.datetime.now() - datetime.timedelta(days=1)).isoformat()))
        notifications_data = [
            ('n_1', 'c_1', '本周二机器人固件配置须知', '请所有加入机器人社的同学...', (datetime.datetime.now() - datetime.timedelta(hours=1)).isoformat()),
            ('n_2', 'c_4', '创意美术社画材自带通知', '本周三集会进行水彩静物写生...', (datetime.datetime.now() - datetime.timedelta(hours=2)).isoformat())
        ]
        cursor.executemany('INSERT INTO notifications VALUES (?,?,?,?,?)', notifications_data)
        db.commit()

# --- Helper ---
def to_dict(row):
    return dict(row) if row else None

# --- Frontend Route ---
@app.route('/')
def index():
    return render_template('社团预约.html')

# --- API Endpoints (No changes below this line) ---
@app.route('/api/user/<user_id>')
def get_user(user_id):
    user = get_db().execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    return jsonify(to_dict(user)) if user else (jsonify({"error": "User not found"}), 404)

@app.route('/api/clubs')
def get_clubs():
    query = """
        SELECT c.*, (SELECT COUNT(*) FROM reservations r WHERE r.club_id = c.club_id AND r.status = 'ACTIVE') as current_capacity 
        FROM clubs c;
    """
    clubs = get_db().execute(query).fetchall()
    return jsonify([to_dict(club) for club in clubs])

@app.route('/api/reservations/<user_id>')
def get_user_reservations(user_id):
    reservations = get_db().execute('SELECT * FROM reservations WHERE user_id = ? AND status = "ACTIVE"', (user_id,)).fetchall()
    return jsonify([to_dict(r) for r in reservations])

@app.route('/api/reserve', methods=['POST'])
def reserve_club():
    data = request.json
    user_id, club_id = data.get('user_id'), data.get('club_id')
    db = get_db()
    
    target_club = db.execute('SELECT * FROM clubs WHERE club_id = ?', (club_id,)).fetchone()
    if not target_club: return jsonify({"error": "Club not found"}), 404

    current_capacity = db.execute('SELECT COUNT(*) FROM reservations WHERE club_id = ? AND status = "ACTIVE"', (club_id,)).fetchone()[0]
    if current_capacity >= target_club['max_capacity']: return jsonify({"error": "名额已满"}), 400

    user_reservations = db.execute("SELECT c.name, c.day_of_week, c.start_time, c.end_time FROM reservations r JOIN clubs c ON r.club_id = c.club_id WHERE r.user_id = ? AND r.status = 'ACTIVE'", (user_id,)).fetchall()
    for res in user_reservations:
        if res['day_of_week'] == target_club['day_of_week'] and not (target_club['end_time'] <= res['start_time'] or target_club['start_time'] >= res['end_time']):
            return jsonify({"error": f"该时间段您已有预约：【{res['name']}】，请先取消原预约。"}), 409

    new_id = 'r_' + str(int(datetime.datetime.now().timestamp()))
    created_time = datetime.datetime.now().isoformat()
    db.execute('INSERT INTO reservations VALUES (?, ?, ?, ?, ?)', (new_id, user_id, club_id, 'ACTIVE', created_time))
    db.commit()
    return jsonify({ "reservation_id": new_id, "user_id": user_id, "club_id": club_id, "status": "ACTIVE", "created_at": created_time }), 201

@app.route('/api/cancel', methods=['POST'])
def cancel_reservation():
    data = request.json
    user_id, club_id = data.get('user_id'), data.get('club_id')
    db = get_db()
    result = db.execute('UPDATE reservations SET status = "CANCELLED" WHERE user_id = ? AND club_id = ? AND status = "ACTIVE"', (user_id, club_id))
    db.commit()
    return jsonify({"message": "已成功取消预约。"}) if result.rowcount > 0 else (jsonify({"error": "Reservation not found"}), 404)

@app.route('/api/notifications/<user_id>')
def get_notifications(user_id):
    db = get_db()
    club_ids_rows = db.execute('SELECT DISTINCT club_id FROM reservations WHERE user_id = ? AND status = "ACTIVE"', (user_id,)).fetchall()
    if not club_ids_rows: return jsonify([])
    
    placeholders = ','.join('?' for _ in club_ids_rows)
    notifications = db.execute(f'SELECT * FROM notifications WHERE club_id IN ({placeholders}) ORDER BY created_at DESC', [r['club_id'] for r in club_ids_rows]).fetchall()
    return jsonify([to_dict(n) for n in notifications])

@app.route('/api/leader/reservations/<leader_id>')
def get_leader_reservations(leader_id):
    db = get_db()
    leader_club = db.execute('SELECT club_id FROM clubs WHERE leader_id = ?', (leader_id,)).fetchone()
    if not leader_club: return jsonify([])

    reservations = db.execute("SELECT r.reservation_id, u.student_id, u.name as studentName, u.class_name, r.created_at FROM reservations r JOIN users u ON r.user_id = u.user_id WHERE r.club_id = ? AND r.status = 'ACTIVE'", (leader_club['club_id'],)).fetchall()
    return jsonify([to_dict(r) for r in reservations])

@app.route('/api/notifications', methods=['POST'])
def publish_notice():
    data = request.json
    leader_id, title, content = data.get('leader_id'), data.get('title'), data.get('content')
    db = get_db()

    leader_club = db.execute('SELECT club_id FROM clubs WHERE leader_id = ?', (leader_id,)).fetchone()
    if not leader_club: return jsonify({"error": "Not a club leader"}), 403

    new_id = 'n_' + str(int(datetime.datetime.now().timestamp()))
    created_time = datetime.datetime.now().isoformat()
    db.execute('INSERT INTO notifications VALUES (?, ?, ?, ?, ?)', (new_id, leader_club['club_id'], title, content, created_time))
    db.commit()
    return jsonify({"notification_id": new_id, "club_id": leader_club['club_id'], "title": title, "content": content, "created_at": created_time}), 201

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5001)
