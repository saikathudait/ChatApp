from waitress import serve
from app import app, socketio

if __name__ == '__main__':
    # Production server for Windows
    print("Starting production server on http://0.0.0.0:5000")
    serve(socketio, host='0.0.0.0', port=5000, threads=4)