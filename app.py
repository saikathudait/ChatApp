

from flask import Flask, render_template_string, request, jsonify, redirect, url_for, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///chat.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)
    
    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# HTML Templates
LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ChatApp - Login</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #128C7E 0%, #25D366 100%);
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .login-container {
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            width: 400px;
        }
        h2 {
            color: #128C7E;
            margin-bottom: 30px;
            text-align: center;
            font-size: 28px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: #333;
            font-weight: 500;
        }
        input {
            width: 100%;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 8px;
            font-size: 14px;
            outline: none;
            transition: border 0.3s;
        }
        input:focus {
            border-color: #25D366;
        }
        button {
            width: 100%;
            padding: 12px;
            background: #25D366;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.3s;
        }
        button:hover {
            background: #20ba5a;
        }
        .switch-form {
            text-align: center;
            margin-top: 20px;
            color: #666;
        }
        .switch-form a {
            color: #128C7E;
            text-decoration: none;
            font-weight: 600;
        }
        .error {
            background: #fee;
            color: #c33;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <h2>{% if register %}Register{% else %}Login{% endif %} to ChatApp</h2>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        <form method="POST">
            <div class="form-group">
                <label>Username</label>
                <input type="text" name="username" required>
            </div>
            <div class="form-group">
                <label>Password</label>
                <input type="password" name="password" required>
            </div>
            <button type="submit">{% if register %}Register{% else %}Login{% endif %}</button>
        </form>
        <div class="switch-form">
            {% if register %}
            Already have an account? <a href="{{ url_for('login') }}">Login here</a>
            {% else %}
            Don't have an account? <a href="{{ url_for('register') }}">Register here</a>
            {% endif %}
        </div>
    </div>
</body>
</html>
'''

CHAT_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ChatApp Web</title>
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: white;
            height: 100vh;
            overflow: hidden;
        }
        .container { display: flex; height: 100vh; }
        
        /* Sidebar */
        .sidebar {
            width: 380px;
            border-right: 1px solid #e0e0e0;
            display: flex;
            flex-direction: column;
            background: #f8f9fa;
        }
        .sidebar-header {
            background: #ededed;
            padding: 15px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #d1d1d1;
        }
        .sidebar-header h2 {
            color: #111;
            font-size: 18px;
        }
        .user-info {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .logout-btn {
            background: #dc3545;
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 12px;
        }
        .search-box {
            padding: 10px;
            background: white;
            border-bottom: 1px solid #e0e0e0;
        }
        .search-box input {
            width: 100%;
            padding: 10px;
            border: 1px solid #e0e0e0;
            border-radius: 20px;
            outline: none;
        }
        .online-users {
            flex: 1;
            overflow-y: auto;
            background: white;
        }
        .user-item {
            padding: 15px;
            border-bottom: 1px solid #f0f0f0;
            cursor: pointer;
            display: flex;
            align-items: center;
            transition: background 0.2s;
        }
        .user-item:hover { background: #f5f5f5; }
        .user-item.active { background: #ebebeb; }
        .avatar {
            width: 50px;
            height: 50px;
            border-radius: 50%;
            background: linear-gradient(135deg, #25D366, #128C7E);
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
            font-size: 20px;
            margin-right: 15px;
        }
        .user-info-text {
            flex: 1;
        }
        .username {
            font-weight: 600;
            color: #111;
            margin-bottom: 3px;
        }
        .status {
            font-size: 12px;
            color: #25D366;
        }
        .unread-badge {
            background: #25D366;
            color: white;
            border-radius: 50%;
            width: 20px;
            height: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            font-weight: bold;
        }
        
        /* Chat Area */
        .chat-area {
            flex: 1;
            display: flex;
            flex-direction: column;
        }
        .welcome-screen {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-direction: column;
            color: #667781;
        }
        .welcome-screen h2 {
            font-size: 32px;
            margin-bottom: 10px;
            color: #111;
        }
        #chatContainer {
            display: none;
            flex: 1;
            flex-direction: column;
        }
        .chat-header {
            background: #ededed;
            padding: 15px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid #d1d1d1;
        }
        .chat-header-left {
            display: flex;
            align-items: center;
        }
        .chat-header-info h3 {
            color: #111;
            font-size: 16px;
        }
        .typing-indicator {
            font-size: 12px;
            color: #667781;
            font-style: italic;
        }
        .messages-area {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            background: #e5ddd5;
            background-image: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23d4cdc6' fill-opacity='0.3'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
        }
        .message {
            margin-bottom: 15px;
            display: flex;
            animation: fadeIn 0.3s;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .message.sent { justify-content: flex-end; }
        .message-bubble {
            max-width: 60%;
            padding: 10px 15px;
            border-radius: 8px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }
        .message.received .message-bubble { background: white; }
        .message.sent .message-bubble { background: #d9fdd3; }
        .message-text {
            color: #111;
            font-size: 14px;
            line-height: 1.5;
            margin-bottom: 3px;
            word-wrap: break-word;
        }
        .message-time {
            font-size: 11px;
            color: #667781;
            text-align: right;
        }
        .input-area {
            background: #f0f0f0;
            padding: 15px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .input-area input {
            flex: 1;
            padding: 12px;
            border: 1px solid #e0e0e0;
            border-radius: 25px;
            outline: none;
            font-size: 14px;
        }
        .send-btn {
            background: #25D366;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 25px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
        }
        .send-btn:hover { background: #20ba5a; }
    </style>
</head>
<body>
    <div class="container">
        <div class="sidebar">
            <div class="sidebar-header">
                <h2>ChatsApp</h2>
                <div class="user-info">
                    <span style="color: #111; font-weight: 600;">{{ current_user.username }}</span>
                    <button class="logout-btn" onclick="logout()">Logout</button>
                </div>
            </div>
            
            <div class="search-box">
                <input type="text" placeholder="Search users..." id="searchInput" oninput="filterUsers()">
            </div>
            
            <div class="online-users" id="usersList"></div>
        </div>
        
        <div class="chat-area">
            <div id="welcomeScreen" class="welcome-screen">
                <h2>Welcome to ChatApp</h2>
                <p>Select a user to start chatting</p>
            </div>
            
            <div id="chatContainer">
                <div class="chat-header">
                    <div class="chat-header-left">
                        <div class="avatar" id="chatHeaderAvatar"></div>
                        <div class="chat-header-info">
                            <h3 id="chatHeaderName"></h3>
                            <div class="typing-indicator" id="typingIndicator" style="display:none;">typing...</div>
                        </div>
                    </div>
                </div>
                
                <div class="messages-area" id="messagesArea"></div>
                
                <div class="input-area">
                    <input type="text" placeholder="Type a message" id="messageInput" onkeypress="handleKeyPress(event)" oninput="handleTyping()">
                    <button class="send-btn" onclick="sendMessage()">Send</button>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        const socket = io();
        const currentUserId = {{ current_user.id }};
        const currentUsername = "{{ current_user.username }}";
        let selectedUserId = null;
        let typingTimeout = null;
        
        socket.on('connect', () => {
            console.log('Connected to server');
            loadUsers();
        });
        
        socket.on('user_list', (data) => {
            displayUsers(data.users);
        });
        
        socket.on('receive_message', (data) => {
            if (data.sender_id === selectedUserId || data.receiver_id === selectedUserId) {
                displayNewMessage(data);
            }
            loadUsers(); // Refresh user list to update last messages
        });
        
        socket.on('user_typing', (data) => {
            if (data.user_id === selectedUserId) {
                document.getElementById('typingIndicator').style.display = 'block';
            }
        });
        
        socket.on('user_stopped_typing', (data) => {
            if (data.user_id === selectedUserId) {
                document.getElementById('typingIndicator').style.display = 'none';
            }
        });
        
        function displayUsers(users) {
            const usersList = document.getElementById('usersList');
            usersList.innerHTML = '';
            
            users.forEach(user => {
                if (user.id !== currentUserId) {
                    const userItem = document.createElement('div');
                    userItem.className = 'user-item' + (user.id === selectedUserId ? ' active' : '');
                    userItem.onclick = () => selectUser(user.id, user.username);
                    
                    const initial = user.username.charAt(0).toUpperCase();
                    let unreadBadge = user.unread_count > 0 ? `<div class="unread-badge">${user.unread_count}</div>` : '';
                    
                    userItem.innerHTML = `
                        <div class="avatar">${initial}</div>
                        <div class="user-info-text">
                            <div class="username">${user.username}</div>
                            <div class="status">online</div>
                        </div>
                        ${unreadBadge}
                    `;
                    
                    usersList.appendChild(userItem);
                }
            });
        }
        
        function loadUsers() {
            fetch('/api/users')
                .then(r => r.json())
                .then(data => displayUsers(data.users));
        }
        
        async function selectUser(userId, username) {
            selectedUserId = userId;
            
            document.getElementById('welcomeScreen').style.display = 'none';
            document.getElementById('chatContainer').style.display = 'flex';
            
            const initial = username.charAt(0).toUpperCase();
            document.getElementById('chatHeaderAvatar').textContent = initial;
            document.getElementById('chatHeaderName').textContent = username;
            
            // Mark messages as read
            await fetch('/api/mark_read', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({user_id: userId})
            });
            
            loadMessages(userId);
            loadUsers(); // Refresh to clear unread badges
            
            document.querySelectorAll('.user-item').forEach(item => {
                item.classList.remove('active');
            });
            event.target.closest('.user-item').classList.add('active');
        }
        
        function loadMessages(userId) {
            fetch(`/api/messages/${userId}`)
                .then(r => r.json())
                .then(data => {
                    const messagesArea = document.getElementById('messagesArea');
                    messagesArea.innerHTML = '';
                    
                    data.messages.forEach(msg => {
                        displayNewMessage(msg);
                    });
                    
                    messagesArea.scrollTop = messagesArea.scrollHeight;
                });
        }
        
        function displayNewMessage(msg) {
            const messagesArea = document.getElementById('messagesArea');
            const messageDiv = document.createElement('div');
            const isSent = msg.sender_id === currentUserId;
            
            messageDiv.className = `message ${isSent ? 'sent' : 'received'}`;
            messageDiv.innerHTML = `
                <div class="message-bubble">
                    <div class="message-text">${escapeHtml(msg.content)}</div>
                    <div class="message-time">${msg.time}</div>
                </div>
            `;
            
            messagesArea.appendChild(messageDiv);
            messagesArea.scrollTop = messagesArea.scrollHeight;
        }
        
        function sendMessage() {
            const input = document.getElementById('messageInput');
            const text = input.value.trim();
            
            if (!text || !selectedUserId) return;
            
            socket.emit('send_message', {
                receiver_id: selectedUserId,
                content: text
            });
            
            input.value = '';
        }
        
        function handleKeyPress(event) {
            if (event.key === 'Enter') {
                sendMessage();
            }
        }
        
        function handleTyping() {
            if (!selectedUserId) return;
            
            socket.emit('typing', {receiver_id: selectedUserId});
            
            clearTimeout(typingTimeout);
            typingTimeout = setTimeout(() => {
                socket.emit('stopped_typing', {receiver_id: selectedUserId});
            }, 1000);
        }
        
        function filterUsers() {
            const searchText = document.getElementById('searchInput').value.toLowerCase();
            const userItems = document.querySelectorAll('.user-item');
            
            userItems.forEach(item => {
                const username = item.querySelector('.username').textContent.toLowerCase();
                item.style.display = username.includes(searchText) ? 'flex' : 'none';
            });
        }
        
        function logout() {
            window.location.href = '/logout';
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    </script>
</body>
</html>
'''

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('chat'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('chat'))
    
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('chat'))
        else:
            error = 'Invalid username or password'
    
    return render_template_string(LOGIN_TEMPLATE, error=error, register=False)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('chat'))
    
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            error = 'Username already exists'
        else:
            user = User(username=username)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for('chat'))
    
    return render_template_string(LOGIN_TEMPLATE, error=error, register=True)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/chat')
@login_required
def chat():
    return render_template_string(CHAT_TEMPLATE)

@app.route('/api/users')
@login_required
def get_users():
    users = User.query.all()
    user_list = []
    
    for user in users:
        unread_count = Message.query.filter_by(
            receiver_id=current_user.id,
            sender_id=user.id,
            read=False
        ).count()
        
        user_list.append({
            'id': user.id,
            'username': user.username,
            'unread_count': unread_count
        })
    
    return jsonify({'users': user_list})

@app.route('/api/messages/<int:user_id>')
@login_required
def get_messages(user_id):
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id)) |
        ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.timestamp).all()
    
    message_list = [{
        'id': msg.id,
        'sender_id': msg.sender_id,
        'receiver_id': msg.receiver_id,
        'content': msg.content,
        'time': msg.timestamp.strftime('%I:%M %p')
    } for msg in messages]
    
    return jsonify({'messages': message_list})

@app.route('/api/mark_read', methods=['POST'])
@login_required
def mark_read():
    data = request.json
    user_id = data.get('user_id')
    
    Message.query.filter_by(
        receiver_id=current_user.id,
        sender_id=user_id,
        read=False
    ).update({'read': True})
    
    db.session.commit()
    return jsonify({'success': True})

# SocketIO Events
@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        join_room(f'user_{current_user.id}')
        emit('user_list', {'users': []}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        leave_room(f'user_{current_user.id}')

@socketio.on('send_message')
def handle_send_message(data):
    if not current_user.is_authenticated:
        return
    
    receiver_id = data.get('receiver_id')
    content = data.get('content')
    
    message = Message(
        sender_id=current_user.id,
        receiver_id=receiver_id,
        content=content
    )
    db.session.add(message)
    db.session.commit()
    
    message_data = {
        'id': message.id,
        'sender_id': current_user.id,
        'receiver_id': receiver_id,
        'content': content,
        'time': message.timestamp.strftime('%I:%M %p')
    }
    
    # Send to both users
    emit('receive_message', message_data, room=f'user_{current_user.id}')
    emit('receive_message', message_data, room=f'user_{receiver_id}')

@socketio.on('typing')
def handle_typing(data):
    if not current_user.is_authenticated:
        return
    
    receiver_id = data.get('receiver_id')
    emit('user_typing', {'user_id': current_user.id}, room=f'user_{receiver_id}')

@socketio.on('stopped_typing')
def handle_stopped_typing(data):
    if not current_user.is_authenticated:
        return
    
    receiver_id = data.get('receiver_id')
    emit('user_stopped_typing', {'user_id': current_user.id}, room=f'user_{receiver_id}')

# Initialize database
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    # For Windows production: python app.py
    # For Linux production: gunicorn -k eventlet -w 1 app:app
    # Change port if 5000 is in use (try 8000, 8080, 3000, etc.)
    port = int(os.environ.get('PORT', 8000))
    print(f"\n🚀 Starting ChatApp Clone on http://localhost:{port}")
    print(f"📱 Open in browser: http://localhost:{port}")
    print(f"🌐 Network access: http://0.0.0.0:{port}\n")
    socketio.run(app, debug=False, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)