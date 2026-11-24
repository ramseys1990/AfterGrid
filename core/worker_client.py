"""Private Unix socket client. The web container has no Docker socket."""
import http.client
import json
import os
import socket

class WorkerUnavailable(Exception):
    pass

class UnixConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(os.environ.get("AFTERGRID_WORKER_SOCKET", "/run/aftergrid/worker.sock"))

def call(path, payload=None, timeout=20):
    conn = UnixConnection("localhost", timeout=timeout)
    try:
        conn.request("GET" if payload is None else "POST", path,
                     body=None if payload is None else json.dumps(payload),
                     headers={"Content-Type": "application/json"})
        response = conn.getresponse()
        return response.status, json.loads(response.read())
    except (OSError, ValueError, http.client.HTTPException) as exc:
        raise WorkerUnavailable("Module manager unavailable") from exc
    finally:
        conn.close()
