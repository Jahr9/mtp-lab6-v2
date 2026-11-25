"""HTTP, шаблоны и общий WebSocket-чат с сохранением сообщений."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Query, Request, WebSocket
from fastapi import WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from lab6.database import Database

ROOT = Path(__file__).resolve().parent


class MessageInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    name: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=1, max_length=1000)


class MessageOutput(MessageInput):
    id: int
    created_at: str


def create_app(db_path=None):
    database = Database(db_path or ROOT.parent / 'data' / 'chat.sqlite3')
    clients = set()

    @asynccontextmanager
    async def lifespan(app):
        database.initialize()
        app.state.broadcast_lock = asyncio.Lock()
        yield
        for socket in list(clients):
            await socket.close(code=1001)
        clients.clear()

    app = FastAPI(title='Лабораторная №6 · Вариант 2', lifespan=lifespan)
    app.state.database = database
    templates = Jinja2Templates(directory=ROOT / 'templates')
    app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')

    def page(request, name, **context):
        return templates.TemplateResponse(request=request, name=name, context=context)

    async def publish(message):
        # Ограничение ожидания исключает зависание на отключившемся клиенте.
        for socket in list(clients):
            try:
                await asyncio.wait_for(socket.send_json({'type': 'message', 'message': message}), 2)
            except (RuntimeError, OSError, WebSocketDisconnect, asyncio.TimeoutError):
                clients.discard(socket)

    async def save_and_publish(data):
        async with app.state.broadcast_lock:
            message = await asyncio.to_thread(database.insert, data.name, data.text)
            await publish(message)
            return message

    @app.get('/', response_class=HTMLResponse)
    def home(request: Request):
        return page(request, 'home.html', greeting=None, error=None)

    @app.post('/greet', response_class=HTMLResponse)
    def greet(request: Request, name: str = Form('')):
        name = name.strip()
        if not 1 <= len(name) <= 40:
            response = page(request, 'home.html', greeting=None,
                            error='Введите имя длиной от 1 до 40 символов.')
            response.status_code = 422
            return response
        return page(request, 'home.html', greeting=f'Привет, {name}!', error=None)

    @app.get('/messages', response_class=HTMLResponse)
    def table(request: Request):
        return page(request, 'messages.html', messages=database.list_messages())

    @app.get('/chat', response_class=HTMLResponse)
    def chat(request: Request):
        return page(request, 'chat.html')

    @app.get('/api/info')
    def info():
        return {'lab': 6, 'variant': 2, 'student': 'Андрюхин Илья Романович',
                'group': '221341', 'database': 'SQLite', 'chat': 'WebSocket'}

    @app.get('/api/messages', response_model=list[MessageOutput])
    def messages(limit: int = Query(100, ge=1, le=100)):
        return database.list_messages(limit)

    @app.get('/api/messages/{message_id}', response_model=MessageOutput)
    def get_message(message_id: int):
        result = database.get(message_id)
        if result is None:
            raise HTTPException(404, 'Сообщение не найдено')
        return result

    @app.post('/api/messages', response_model=MessageOutput, status_code=201)
    async def post_message(data: MessageInput):
        return await save_and_publish(data)

    @app.websocket('/ws')
    async def websocket_chat(socket: WebSocket):
        await socket.accept()
        try:
            # История и регистрация атомарны относительно новых сообщений.
            async with app.state.broadcast_lock:
                history = await asyncio.to_thread(database.list_messages)
                await socket.send_json({'type': 'history', 'messages': history})
                clients.add(socket)
            while True:
                raw = await socket.receive_text()
                if len(raw) > 8192:
                    await socket.send_json({'type': 'error', 'detail': 'Сообщение слишком большое.'})
                    continue
                try:
                    data = MessageInput.model_validate_json(raw)
                except ValidationError:
                    await socket.send_json({'type': 'error', 'detail':
                                            'Имя: 1–40 символов; текст: 1–1000 символов.'})
                    continue
                await save_and_publish(data)
        except WebSocketDisconnect:
            pass
        finally:
            clients.discard(socket)

    return app
