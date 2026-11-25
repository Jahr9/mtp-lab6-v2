'use strict';
const log = document.getElementById('messages');
const statusNode = document.getElementById('status');
const errorNode = document.getElementById('error');
const send = document.getElementById('send');
let socket;
let seen = new Set();
function append(message) {
  if (seen.has(message.id)) return;
  seen.add(message.id);
  document.getElementById('empty')?.remove();
  const item = document.createElement('article'); item.className = 'bubble';
  const author = document.createElement('strong'); author.textContent = message.name;
  const text = document.createElement('p'); text.textContent = message.text;
  const time = document.createElement('small'); time.textContent = new Date(message.created_at).toLocaleString();
  item.append(author, text, time); log.append(item); log.scrollTop = log.scrollHeight;
}
function connect() {
  if (socket) socket.close();
  const current = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  socket = current; send.disabled = true; statusNode.textContent = 'Подключение…';
  current.onopen = () => { if(socket !== current) return; statusNode.textContent = 'В сети'; send.disabled = false; errorNode.textContent = ''; };
  current.onmessage = event => {
    if(socket !== current) return;
    const data = JSON.parse(event.data);
    if (data.type === 'history') {
      log.replaceChildren(); seen = new Set();
      if (!data.messages.length) {const empty = document.createElement('p'); empty.id = 'empty'; empty.textContent = 'Сообщений пока нет.'; log.append(empty);}
      data.messages.forEach(append);
    }
    if (data.type === 'message') append(data.message);
    if (data.type === 'error') errorNode.textContent = data.detail;
  };
  current.onclose = () => {if(socket !== current) return; statusNode.textContent = 'Нет соединения'; send.disabled = true;};
  current.onerror = () => {if(socket === current) errorNode.textContent = 'Не удалось подключиться. Проверьте сервер и нажмите «Переподключить».';};
}
document.getElementById('reconnect').onclick = connect;
document.getElementById('chat-form').onsubmit = event => {
  event.preventDefault();
  const name = document.getElementById('author').value.trim();
  const input = document.getElementById('text'); const text = input.value.trim();
  if (!name || !text) {errorNode.textContent = 'Введите имя и сообщение.'; return;}
  if (!socket || socket.readyState !== WebSocket.OPEN) {errorNode.textContent = 'Нет соединения с сервером.'; return;}
  socket.send(JSON.stringify({name, text})); input.value = ''; input.focus(); errorNode.textContent = '';
};
connect();
