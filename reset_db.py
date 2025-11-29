import os
from app import app, db

# Delete old database
if os.path.exists('chat.db'):
    os.remove('chat.db')
    print("✅ Old database deleted")

# Create new database
with app.app_context():
    db.create_all()
    print("✅ New database created successfully!")