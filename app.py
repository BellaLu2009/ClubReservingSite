import sqlite3
import datetime
import json
from flask import Flask, jsonify, request, g, render_template
from flask_cors import CORS
import os
from werkzeug.security import generate_password_hash, check_password_hash

# --- App & DB Setup ---
app = Flask(__name__)
CORS(app)
DATABASE = 'club_booking.db'

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE, check_same_thread=False)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    if hasattr(g, 'db'):
        g.db.close()

def init_db():
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
        
        hashed_password = generate_password_hash('123456')
        cursor.execute('INSERT INTO users VALUES (?,?,?,?,?,?,?,?)', ('u_01', 'zhangsan', hashed_password, '张三', '高二(3)班', '2026020315', 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=120&auto=format&fit=crop&q=80', '["STUDENT", "CLUB_LEADER"]'))
        clubs_data = [
            ("c_1", "机器人实验室", "ACADEMIC", "探索 VEX 机器人工程架构...", "u_01", "综合楼402", 1, 2, "16:00:00", "17:30:00"), # Reduced capacity for testing
            ("c_2", "潮流篮球社", "SPORTS", "高强度全场战术配合...", "u_other", "室内体育馆A厅", 30, 4, "16:00:00", "17:30:00"),
            ("c_3", "青年志愿者协会", "PUBLIC_WELFARE", "参与社区服务和公益活动，传递爱心。", "u_other", "学生活动中心", 40, 1, "17:30:00", "19:00:00"),
            ("c_4", "校园环保社", "PUBLIC_WELFARE", "组织校园环保活动，宣传环保理念。", "u_other", "校园广场", 35, 3, "16:00:00", "17:30:00"),
            ("c_5", "室内羽毛球社", "SPORTS", "提供专业级木地板场地...", "u_other", "羽毛球馆3号场", 20, 2, "16:00:00", "17:30:00")
        ]
        cursor.executemany('INSERT INTO clubs VALUES (?,?,?,?,?,?,?,?,?,?)', clubs_data)
        db.commit()

# --- Helper ---
def to_dict(row):
    return dict(row) if row else None

# --- Frontend Routes ---
@app.route('/')
def index():
    return render_template('社团预约.html')

@app.route('/admin')
def admin_panel():
    return render_template('admin.html')

# --- API Endpoints ---
@app.route('/api/user/<user_id>')
def get_user(user_id):
    user_row = get_db().execute('SELECT user_id, username, name, class_name, student_id, avatar_url, roles FROM users WHERE user_id = ?', (user_id,)).fetchone()
    if not user_row:
        return jsonify({"error": "User not found"}), 404
    user_dict = to_dict(user_row)
    if user_dict.get('roles'):
        user_dict['roles'] = json.loads(user_dict['roles'])
    return jsonify(user_dict)

@app.route('/api/user/password', methods=['PUT'])
def update_password():
    data = request.json
    user_id, old_password, new_password = data.get('user_id'), data.get('old_password'), data.get('new_password')
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    if not user or not check_password_hash(user['password_hash'], old_password):
        return jsonify({"error": "旧密码不正确"}), 400
    
    new_password_hash = generate_password_hash(new_password)
    db.execute('UPDATE users SET password_hash = ? WHERE user_id = ?', (new_password_hash, user_id))
    db.commit()
    return jsonify({"message": "密码更新成功！"})

@app.route('/api/clubs')
def get_clubs():
    query = """
        SELECT 
            c.*, 
            (SELECT COUNT(*) FROM reservations r WHERE r.club_id = c.club_id AND r.status = 'ACTIVE') as current_capacity,
            (SELECT COUNT(*) FROM reservations r WHERE r.club_id = c.club_id AND r.status = 'WAITLISTED') as waitlist_count
        FROM clubs c;
    """
    clubs = get_db().execute(query).fetchall()
    return jsonify([to_dict(club) for club in clubs])

@app.route('/api/reservations/<user_id>')
def get_user_reservations(user_id):
    reservations = get_db().execute('SELECT * FROM reservations WHERE user_id = ?', (user_id,)).fetchall()
    return jsonify([to_dict(r) for r in reservations])

@app.route('/api/reserve', methods=['POST'])
def reserve_club():
    data = request.json
    user_id, club_id = data.get('user_id'), data.get('club_id')
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
def cancel_reservation():
    data = request.json
    user_id, club_id = data.get('user_id'), data.get('club_id')
    db = get_db()
    
    result = db.execute('DELETE FROM reservations WHERE user_id = ? AND club_id = ?', (user_id, club_id))
    if result.rowcount == 0: return jsonify({"error": "未找到您的预约记录"}), 404

    # Promote a user from waitlist if there's an opening
    waitlisted_user = db.execute("SELECT * FROM reservations WHERE club_id = ? AND status = 'WAITLISTED' ORDER BY created_at ASC LIMIT 1", (club_id,)).fetchone()
    if waitlisted_user:
        db.execute("UPDATE reservations SET status = 'ACTIVE' WHERE reservation_id = ?", (waitlisted_user['reservation_id'],))
        # Here you could add a notification for the promoted user
    
    db.commit()
    return jsonify({"message": "已成功取消。"})

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

    reservations = db.execute("SELECT r.reservation_id, u.student_id, u.name as studentName, u.class_name, r.created_at, r.status FROM reservations r JOIN users u ON r.user_id = u.user_id WHERE r.club_id = ? ORDER BY r.status, r.created_at", (leader_club['club_id'],)).fetchall()
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
    app.run(host='0.0.0.0', debug=True, port=5001)