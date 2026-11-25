"""HTTP, SQLite и реальный протокол WebSocket через TestClient."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient
from lab6.app import create_app


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'test.sqlite3'
        self.app = create_app(self.path)
        self.client = self.enterContext(TestClient(self.app))

    def test_home_and_assets(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        for path in ('/static/style.css', '/static/chat.js', '/chat', '/docs'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_greeting(self):
        response = self.client.post('/greet', data={'name': ' Илья '})
        self.assertEqual(response.status_code, 200)
        self.assertIn('Привет, Илья!', response.text)

    def test_invalid_greeting(self):
        for name in ('', '   ', 'a' * 41):
            self.assertEqual(self.client.post('/greet', data={'name': name}).status_code, 422)

    def test_greeting_escapes_html(self):
        response = self.client.post('/greet', data={'name': '<script>alert(1)</script>'})
        self.assertNotIn('<script>alert(1)</script>', response.text)
        self.assertIn('&lt;script&gt;', response.text)

    def test_json_info(self):
        response = self.client.get('/api/info')
        self.assertIn('application/json', response.headers['content-type'])
        self.assertEqual(response.json()['variant'], 2)
        self.assertEqual(response.json()['lab'], 6)

    def test_insert_and_get(self):
        response = self.client.post('/api/messages', json={'name': 'Илья', 'text': 'Привет'})
        self.assertEqual(response.status_code, 201)
        saved = response.json()
        self.assertEqual(self.client.get(f"/api/messages/{saved['id']}").json(), saved)
        self.assertEqual(self.client.get('/api/messages').json(), [saved])

    def test_invalid_message(self):
        cases = [{'name': '', 'text': 'a'}, {'name': 'x', 'text': ' '},
                 {'name': 'x' * 41, 'text': 'a'}, {'name': 'x', 'text': 'a' * 1001},
                 {'name': 'x', 'text': 12}, {'name': 'x', 'text': 'a', 'extra': 1}]
        for data in cases:
            with self.subTest(data=str(data)[:50]):
                self.assertEqual(self.client.post('/api/messages', json=data).status_code, 422)
        self.assertEqual(self.client.get('/api/messages').json(), [])

    def test_not_found_and_limit(self):
        self.assertEqual(self.client.get('/api/messages/999').status_code, 404)
        for limit in (0, 101, 'abc'):
            self.assertEqual(self.client.get(f'/api/messages?limit={limit}').status_code, 422)

    def test_table_and_escaping(self):
        self.assertIn('Сообщений пока нет', self.client.get('/messages').text)
        self.client.post('/api/messages', json={'name': 'Илья', 'text': '<script>bad()</script>'})
        response = self.client.get('/messages')
        self.assertIn('<table>', response.text)
        self.assertIn('Илья', response.text)
        self.assertIn('&lt;script&gt;', response.text)
        self.assertNotIn('<script>bad()', response.text)

    def test_sql_injection_is_plain_text(self):
        text = "'); DROP TABLE messages; --"
        self.client.post('/api/messages', json={'name': 'Олег', 'text': text})
        self.assertEqual(self.client.get('/api/messages').json()[0]['text'], text)

    def test_persistence_new_application(self):
        self.client.post('/api/messages', json={'name': 'Илья', 'text': 'Сохранено'})
        with TestClient(create_app(self.path)) as reopened:
            self.assertEqual(reopened.get('/api/messages').json()[0]['text'], 'Сохранено')

    def test_recent_messages_order(self):
        for text in ('one', 'two', 'three'):
            self.client.post('/api/messages', json={'name': 'x', 'text': text})
        self.assertEqual([m['text'] for m in self.client.get('/api/messages?limit=2').json()],
                         ['two', 'three'])

    def test_websocket_two_clients(self):
        with self.client.websocket_connect('/ws') as a, self.client.websocket_connect('/ws') as b:
            self.assertEqual(a.receive_json(), {'type': 'history', 'messages': []})
            b.receive_json()
            a.send_json({'name': 'Илья', 'text': 'Первое сообщение'})
            first = a.receive_json()
            self.assertEqual(b.receive_json(), first)
            self.assertEqual(first['message']['text'], 'Первое сообщение')
            b.send_json({'name': 'Олег', 'text': 'Ответ'})
            self.assertEqual(a.receive_json(), b.receive_json())
        self.assertEqual(len(self.client.get('/api/messages').json()), 2)

    def test_reconnect_history(self):
        with self.client.websocket_connect('/ws') as ws:
            ws.receive_json()
            ws.send_json({'name': 'Илья', 'text': 'История'})
            sent = ws.receive_json()['message']
        with self.client.websocket_connect('/ws') as ws:
            self.assertEqual(ws.receive_json()['messages'], [sent])

    def test_websocket_validation_and_recovery(self):
        with self.client.websocket_connect('/ws') as ws:
            ws.receive_json()
            for raw in ('not json', '{"name":"x","text":" "}', 'x' * 8193):
                ws.send_text(raw)
                self.assertEqual(ws.receive_json()['type'], 'error')
            ws.send_json({'name': 'Илья', 'text': 'Работает'})
            self.assertEqual(ws.receive_json()['type'], 'message')

    def test_http_message_broadcast(self):
        with self.client.websocket_connect('/ws') as ws:
            ws.receive_json()
            response = self.client.post('/api/messages', json={'name': 'API', 'text': 'Из HTTP'})
            self.assertEqual(ws.receive_json()['message'], response.json())
