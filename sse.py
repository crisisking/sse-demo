"""Protocol implementation for HTTP server-sent events."""

import json
import time

import collections

from gevent.queue import Queue


class Closed(Exception):
    """Exception raised when operations are attempted
    on a closed client connection."""


class Client(Queue):
    """A closable gevent queue / client object.
    This adds a close method because gevent calls
    close on the iterable returned by a wsgi app
    to signal the end of a request."""

    def __init__(self, username, *args, **kwargs):
        self._closed = False
        self.events = set()
        self.username = username
        super(Client, self).__init__(*args, **kwargs)

    @property
    def closed(self):
        """True if the client's connection is closed, false otherwise."""
        return self._closed

    def close(self, clear_events=True):
        """Closes the client, preventing any further data from
        being queued."""
        if self.closed:
            raise Closed('Connection is already closed.')
        self.put(StopIteration)
        self._closed = True
        for event in self.events:
            event.remove_listener(self)
        message = json.dumps({'user': self.username, 'text': 'left the chat'})
        for event in self.events:
            event.send_event(message, msg_id=time.time())
        if clear_events:
            self.events.clear()

    def put(self, *args, **kwargs):
        """Puts data in the client's outgoing queue.
        Raises a Closed exception if the client is closed."""
        if self.closed:
            raise Closed('Connection is closed.')
        super(Client, self).put(*args, **kwargs)

    def listen(self, event, last_event_id=None):
        """Tells an event source that this client
        wants to listen to it."""
        self.events.add(event)
        event.register_listener(self, last_event_id)

    def forget(self, event):
        """Stop listening to an event source."""
        self.events.remove(event)
        event.remove_listener(self)


class EventSource(object):
    """An event generator. Broadcasts messages to
     all listening clients."""

    def __init__(self):
        self.listeners = set()
        self.history = collections.deque(maxlen=10)

    def send_event(self, data, msg_id=None, event=None, add_to_history=True):
        """Broadcasts an event to all listening clients."""
        if event is None:
            event = ''
        else:
            event = 'event:%s' % event

        data = 'data:%s' % data

        if msg_id is None:
            msg_id = ''
            _id = 0.0
        else:
            _id = msg_id
            msg_id = 'id:%s' % str(msg_id)

        message = ('\n'.join([event, data, msg_id, '\n'])).lstrip('\n')

        closed = set()
        for listener in self.listeners:
            try:
                listener.put(message)
            except Closed:
                closed.add(listener)
        self.listeners.difference_update(closed)

        if add_to_history:
            self.history.append((_id, message))

    def register_listener(self, listener, last_event_id=None):
        """Registers a client for event broadcasts."""
        if listener in self.listeners:
            return
        if last_event_id is not None:
            events = [event[1] for event in self.history
                      if event[0] >= last_event_id]
            for event in events:
                listener.put_nowait(event)
        self.listeners.add(listener)

    def remove_listeners(self, listeners):
        """Stop broadcasting events to the given clients."""
        self.listeners.difference_update(listeners)

    def remove_listener(self, listener):
        """Stop broadcasting events to the given client."""
        self.listeners.remove(listener)

    def cleanup_closed_listeners(self):
        """Removes all closed clients from the known client list."""
        closed_listeners = [listener for listener in self.listeners
                            if listener.closed]
        self.remove_listeners(closed_listeners)
