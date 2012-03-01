import gevent.monkey
gevent.monkey.patch_all()

import cgi
import time
import json
import urllib
import weakref
import urlparse

from gevent.pywsgi import WSGIServer

from sse import Client, EventSource

CLIENTS = weakref.WeakSet()
CHANNELS = {'default': EventSource()}

INDEX_FILE = open('chat.html', 'rb')
INDEX = INDEX_FILE.read()
INDEX_FILE.close()


def application(environ, start_response):
    if environ['PATH_INFO'] in ('', '/', '/index.html'):
        start_response('200 OK', [('Content-type', 'text/html; charset=utf8')])
        return INDEX
    elif environ['PATH_INFO'] == '/events/':
        start_response('200 OK', [('Content-type', 'text/event-stream')])
        query_string = dict(urlparse.parse_qsl(environ.get('QUERY_STRING', [])))
        username = query_string.get('username', 'A BIG DUMMY')
        username = urllib.unquote_plus(username).decode('utf8')
        username = cgi.escape(username).encode('ascii', 'xmlcharrefreplace')
        client = Client(username)
        client.listen(CHANNELS['default'])
        CLIENTS.add(client)
        message = json.dumps({'user': username, 'text': 'joined the chat'})
        CHANNELS['default'].send_event(message, msg_id=time.time())
        return client
    elif environ['PATH_INFO'] == '/commands/':
        start_response('200 OK', [('Content-type', 'text/plain')])
        content_length = environ.get('CONTENT_LENGTH', 0)
        if not content_length:
            return ''
        content_length = int(content_length)
        content = environ['wsgi.input'].read(content_length)
        content = urlparse.parse_qsl(content)
        content = dict(content)
        for key in content:
            content[key] = urllib.unquote(content[key]).decode('utf8')
            content[key] = cgi.escape(content[key]).encode('ascii', 'xmlcharrefreplace')
        message = json.dumps({'user': content['user'], 'text': content['msg']})
        CHANNELS['default'].send_event(message, msg_id=time.time())
        return ''
    else:
        start_response('404 Not Found', [])
        return ''


if __name__ == '__main__':
    def monitor():
        while True:
            msg = json.dumps({'user': 'system', 'text': 'ping'})
            CHANNELS['default'].send_event(msg, msg_id=time.time(), event='ping', add_to_history=False)
            msg = json.dumps({'user_count': len(CLIENTS), 'users': [c.username for c in CLIENTS]})
            CHANNELS['default'].send_event(msg, event='count', add_to_history=False)
            gevent.sleep(5)
    gevent.spawn(monitor)
    server = WSGIServer(('', 9500), application)
    server.serve_forever()
