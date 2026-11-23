"""Loopback-only feedback relay. Webhook is private server environment, never a client field."""
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PRODUCT_NAME = "捞鱼火花管家"


def scrub(text):
    text = str(text or '')
    text = re.sub(r'(?i)(token|password|passwd|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+', r'\1=[redacted]', text)
    text = re.sub(r'(?i)Bearer\s+\S+', 'Bearer [redacted]', text)
    text = re.sub(r'[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}', '[email]', text)
    text = re.sub(r'[a-zA-Z]:[\\/][^\r\n]+', '[local path]', text)
    return text


def chunks(text, limit=1700):
    parts, current, size = [], [], 0
    for char in text:
        count = len(char.encode('utf-8'))
        if size + count > limit:
            parts.append(''.join(current)); current, size = [], 0
        current.append(char); size += count
    if current: parts.append(''.join(current))
    return parts


class Relay:
    def __init__(self, database, sender, clock=time.time):
        self.db = sqlite3.connect(database, check_same_thread=False)
        self.db.execute('PRAGMA max_page_count=2048')
        self.db.execute('CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY, digest TEXT, state TEXT, created REAL)')
        self.sender, self.clock, self.lock = sender, clock, threading.Lock()
        self.rates = {}

    def submit(self, payload, client):
        if not isinstance(payload, dict) or not re.fullmatch(r'[a-f0-9-]{36}', str(payload.get('request_id', ''))):
            return 400, {'errcode': 1, 'error': 'invalid_request'}
        if payload.get('msgtype') != 'text' or not isinstance(payload.get('text'), dict):
            return 400, {'errcode': 1, 'error': 'invalid_message'}
        content = payload['text'].get('content')
        if not isinstance(content, str) or not content.strip() or len(content.encode('utf-8')) > 9000:
            return 400, {'errcode': 1, 'error': 'invalid_length'}
        content = scrub(content)
        if not content.startswith(PRODUCT_NAME + ' '):
            return 400, {'errcode': 1, 'error': 'invalid_product'}
        request_id = payload['request_id']
        digest = hashlib.sha256(content.encode('utf-8')).hexdigest()
        now = self.clock()
        with self.lock:
            row = self.db.execute('SELECT digest,state FROM receipts WHERE id=?', (request_id,)).fetchone()
            if row:
                if row[0] != digest: return 409, {'errcode': 1, 'error': 'request_id_conflict'}
                return (200 if row[1] == 'delivered' else 409), {'errcode': 0 if row[1] == 'delivered' else 1, 'state': row[1], 'request_id': request_id, 'duplicate':True}
            self.rates = {k:v for k,v in self.rates.items() if now-v < 60}
            if now-self.rates.get(client, -1000) < 30 or sum(k.startswith('global:') for k in self.rates) >= 3:
                return 429, {'errcode': 1, 'error': 'rate_limited'}
            self.rates[client] = now; self.rates['global:'+request_id] = now
            self.db.execute('DELETE FROM receipts WHERE created<?', (now-86400,))
            self.db.execute('INSERT INTO receipts VALUES (?,?,?,?)', (request_id,digest,'pending',now)); self.db.commit()
        state = 'unknown'
        try:
            parts = chunks(content)
            for index, part in enumerate(parts):
                body = {'msgtype':'text','text':{'content':f'{PRODUCT_NAME} 反馈 {request_id} {index+1}/{len(parts)}\n'+part}}
                response = self.sender(body)
                if response.get('errcode') != 0:
                    state = 'failed' if index == 0 else 'partial'; break
            else: state = 'delivered'
        except Exception:
            # No automatic resend: an HTTP timeout can occur after actual delivery.
            state = 'unknown'
        with self.lock:
            self.db.execute('UPDATE receipts SET state=? WHERE id=?', (state,request_id)); self.db.commit()
        return (200 if state == 'delivered' else 502), {'errcode':0 if state == 'delivered' else 1,'state':state,'request_id':request_id}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def upstream_sender(url):
    if not re.fullmatch(r'https://qyapi\.weixin\.qq\.com/cgi-bin/webhook/send\?key=[a-zA-Z0-9_-]{12,100}', url):
        raise ValueError('private upstream configuration is required')
    def send(body):
        request = urllib.request.Request(url, data=json.dumps(body,ensure_ascii=False).encode('utf-8'), headers={'Content-Type':'application/json'})
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=8) as response:
            return json.loads(response.read(16384))
    return send


def handler(relay):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass  # No IPs, messages, secrets or access logs.
        def setup(self):
            super().setup(); self.connection.settimeout(10)
        def reply(self, status, body):
            data=json.dumps(body).encode('utf-8'); self.send_response(status)
            self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def do_GET(self):
            self.reply(200,{'status':'ready','product':'xuhuohua'}) if self.path=='/health' else self.reply(404,{'errcode':1})
        def do_POST(self):
            if self.path != '/feedback': return self.reply(404,{'errcode':1})
            try:
                if self.headers.get('Transfer-Encoding'):raise ValueError()
                length=int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 12000:raise ValueError()
                payload=json.loads(self.rfile.read(length).decode('utf-8'))
                # Only nginx on loopback can reach this listener. Nginx overwrites X-Real-IP.
                client=hashlib.sha256(self.headers.get('X-Real-IP',self.client_address[0]).encode()).hexdigest()
                status,result=relay.submit(payload,client);self.reply(status,result)
            except (ValueError,UnicodeError):self.reply(400,{'errcode':1,'error':'invalid_request'})
    return Handler


class BoundedServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.slots=threading.BoundedSemaphore(8)
    def process_request(self,request,address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request);return
        try:super().process_request(request,address)
        except Exception:self.slots.release();raise
    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.slots.release()
    def handle_error(self,request,address):
        # The stdlib default prints the peer IP and stack; neither is needed here.
        import sys
        print('feedback request failed',file=sys.stderr)


if __name__ == '__main__':
    relay=Relay(os.environ.get('FEEDBACK_DATABASE','/var/lib/xuhuohua-feedback/receipts.sqlite3'),upstream_sender(os.environ.get('FEEDBACK_WEBHOOK','')))
    BoundedServer(('127.0.0.1',18775),handler(relay)).serve_forever()
