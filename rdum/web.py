"""Local web interface for a Bluetooth or serial-connected meter."""

import argparse
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources

from . import controller
from .tool import RDUMTool


class DeviceServer(ThreadingHTTPServer):
    def __init__(self, address, device, device_type):
        super().__init__(address, WebHandler)
        self.device = device
        self.device_type = device_type
        self.device_lock = threading.Lock()


class WebHandler(BaseHTTPRequestHandler):
    server: DeviceServer

    def send_content(self, status, content_type, body):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, data):
        self.send_content(status, 'application/json; charset=utf-8', json.dumps(data).encode('utf-8'))

    def valid_host(self):
        return self.headers.get('Host') == '127.0.0.1:{}'.format(self.server.server_port)

    def do_GET(self):
        if not self.valid_host():
            self.send_json(400, {'error': 'Invalid host'})
            return
        if self.path == '/api/status':
            try:
                with self.server.device_lock:
                    response = controller.read_response(self.server.device, self.server.device_type)
                self.send_json(200, {
                    'device_type': self.server.device_type,
                    'measurements': controller.response_dict(response),
                })
            except (OSError, ValueError, RuntimeError) as exc:
                logging.exception('Device read failed')
                self.send_json(502, {'error': 'Device read failed: {}'.format(exc)})
            return
        files = {
            '/': ('index.html', 'text/html; charset=utf-8'),
            '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
            '/style.css': ('style.css', 'text/css; charset=utf-8'),
        }
        if self.path not in files:
            self.send_json(404, {'error': 'Not found'})
            return
        name, content_type = files[self.path]
        body = resources.files('rdum').joinpath('webfiles', name).read_bytes()
        self.send_content(200, content_type, body)

    def do_POST(self):
        expected_origin = 'http://127.0.0.1:{}'.format(self.server.server_port)
        if not self.valid_host() or self.headers.get('Origin') != expected_origin:
            self.send_json(403, {'error': 'Invalid origin or host'})
            return
        if self.path != '/api/command':
            self.send_json(404, {'error': 'Not found'})
            return
        if self.headers.get_content_type() != 'application/json':
            self.send_json(415, {'error': 'Expected application/json'})
            return
        try:
            length = int(self.headers.get('Content-Length', ''))
            if not 0 < length <= 1024:
                raise ValueError('Invalid request length')
            request = json.loads(self.rfile.read(length))
            if not isinstance(request, dict) or set(request) != {'command', 'value'}:
                raise ValueError('Expected command and value')
            name, value = request['command'], request['value']
            if not isinstance(name, str):
                raise ValueError('Command must be a string')
            controller.command_bytes(name, value, self.server.device_type)
        except (ValueError, UnicodeDecodeError) as exc:
            self.send_json(400, {'error': str(exc)})
            return
        try:
            with self.server.device_lock:
                controller.send_command(self.server.device, name, value, self.server.device_type)
        except (OSError, RuntimeError) as exc:
            logging.exception('Device command failed')
            self.send_json(502, {'error': 'Device command failed: {}'.format(exc)})
            return
        self.send_json(200, {'ok': True})


def main(argv=None):
    parser = argparse.ArgumentParser(description='Local web interface for an RDTech USB meter')
    parser.add_argument('--device-type', choices=controller.MODELS, default='UM24C')
    devices = parser.add_mutually_exclusive_group()
    devices.add_argument('--bluetooth-device', help='Bluetooth MAC address')
    devices.add_argument('--serial-device', help='Serial port, e.g. /dev/rfcomm0')
    parser.add_argument('--port', type=int, default=8765, help='Local HTTP port (default: 8765)')
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error('port must be between 0 and 65535')

    logging.basicConfig(level=logging.INFO, format='%(message)s')
    tool = RDUMTool()
    tool.args = args
    tool.setup_device()
    try:
        with DeviceServer(('127.0.0.1', args.port), tool.dev, args.device_type) as server:
            print('Open http://127.0.0.1:{}/ (Ctrl-C to stop)'.format(server.server_port), flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
    finally:
        tool.dev.close()


if __name__ == '__main__':
    main()
