"""Запуск локального учебного сервера: python main.py."""
import uvicorn
from lab6.app import create_app

app = create_app()

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=8000, ws_max_size=16384)
