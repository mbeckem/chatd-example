#!/usr/bin/env python3

import logging
logging.basicConfig(level=logging.DEBUG,
                    format="%(asctime)s %(name)-15s %(levelname)-8s %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

import asyncio
import collections
import json
import os

import aiohttp
from aiohttp import web

DEFAULT_PORT = 5000

ROOT_DIR = os.path.dirname(os.path.realpath(__file__))
ASSETS_DIR = os.path.join(ROOT_DIR, "assets")
INDEX_PATH = os.path.join(ROOT_DIR, "index.html")


def make_message(author, message):
    return json.dumps({"author": author, "message": message})

def ignore_result(task):
    if not task.cancelled():
        task.exception() # mark as observed
        

class Application:
    def __init__(self):
        self._app = web.Application()
        self._app.add_routes([
            web.get("/", self.handle_index),
            web.get("/session", self.handle_session),
            web.static("/assets", ASSETS_DIR)
        ])
        self._app.cleanup_ctx.append(lambda app: self.status_loop_setup(app))
        
        self._session_count = 1
        self._room = ChatRoom()
        
    def run(self):
        web.run_app(self._app, port = DEFAULT_PORT)

    async def status_loop_setup(self, app):
        task = asyncio.create_task(self.status_loop())
        yield
        task.cancel()
        await task

    async def status_loop(self):
        try:
            while True:
                logger.info("Sessions: %s, Tasks: %s" % (self._room.session_count(), len(asyncio.all_tasks())))
                await asyncio.sleep(15 * 60)
        except asyncio.CancelledError:
            pass

    async def handle_index(self, request):
        with open(INDEX_PATH, "r", encoding = "utf-8") as f:
            html = f.read()
        return web.Response(text = html, content_type = "text/html", charset = "utf-8")
    
    # Receives a websocket connection
    async def handle_session(self, request):
        ws = web.WebSocketResponse(heartbeat = 60.0)
        await ws.prepare(request)
        
        name = f"User#{self._session_count}"
        self._session_count += 1
        
        session = ChatSession(name, ws)
        try:
            await session.run(self._room)
        finally:
            await ws.close()
        return ws
                    

# Keeps a set of connected sessions. All messages are sent to every member of the room.
class ChatRoom:
    def __init__(self):
        self._sessions = set()

    def session_count(self):
        return len(self._sessions)

    def register(self, session):
        assert session not in self._sessions
        self._sessions.add(session)
        self.send(make_message("SYSTEM", f"{session.name()} has joined the room."))

    def unregister(self, session):
        assert session in self._sessions
        self._sessions.remove(session)
        self.send(make_message("SYSTEM", f"{session.name()} has left the room."))
        
    def send(self, message):
        for session in self._sessions:
            session.send(message)
            

# Reads incoming json messages from the web socket and writes them to other clients.
# Also writes outgoing json messages from the message queue to the web socket.
class ChatSession:
    MAX_MESSAGES = 100
    
    def __init__(self, name, socket):
        self._name = name
        self._socket = socket
        self._read_task = None
        self._write_task = None
        self._queue_event = asyncio.Event()
        self._message_queue = collections.deque()
        
    def name(self):
        return self._name
        
    async def run(self, room):        
        self._write_task = asyncio.create_task(self.write())
        self._write_task.add_done_callback(ignore_result)
        self._read_task = asyncio.current_task()
                
        # Read incoming messages until an error occurs or we get cancelled.
        try:
            room.register(self)
            
            async for frame in self._socket:
                if frame.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(frame.data)
                    if data["type"] == "message":
                        message = make_message(self._name, data["message"])
                        room.send(message)
                    else:
                        logger.error("Invalid data type: %s", data["type"])
                elif frame.type == aiohttp.WSMsgType.ERROR:
                    logger.error("WebSocket connection closed with error %s" % ws.exception())
                    break
                
        except asyncio.CancelledError:
            # logger.info(f"Reader cancelled: {self.name()}")
            raise
        except Exception:
            logger.exception("Error within a session.")
        finally:
            room.unregister(self)
            if not self._write_task.done() and not self._write_task.cancelled():
                self._write_task.cancel()
            # logger.info(f"Reader stopped: {self.name()}")


    # Sends a message to the client. Client's that are too slow to drain
    ## their queue get disconnected.
    def send(self, message):
        if len(self._message_queue) >= ChatSession.MAX_MESSAGES:
            logger.info("Disconnecting client because it was too slow.")
            self.stop()
            return
        
        # Insert the message and wake the task
        was_empty = len(self._message_queue) == 0
        self._message_queue.append(message)
        if was_empty and not self._queue_event.is_set():
            self._queue_event.set()
            
    # Writes from the queue to the client's web socket.
    async def write(self):
        try:
            while True:
                await self._queue_event.wait()
                assert len(self._message_queue) > 0
                
                message = self._message_queue.popleft()
                if not self._message_queue:
                    self._queue_event.clear()
                
                await self._socket.send_str(message)
        except asyncio.CancelledError:
            # logger.info(f"Writer cancelled: {self.name()}")
            raise
        except Exception:
            logger.exception("Error writing to web socket.")
            self.stop()
        finally:
            # logger.info(f"Writer stopped: {self.name()}")
            pass


    # Cancel both tasks
    def stop(self):
        if not self._read_task.done() and not self._read_task.cancelled():
            self._read_task.cancel()


if __name__ == "__main__":    
    app = Application()
    app.run()
