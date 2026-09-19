import os
from waitress import serve
from app import app

if __name__ == '__main__':
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', '8080'))
    serve(app, host=host, port=port, threads=int(os.environ.get('WAITRESS_THREADS', '8')))
