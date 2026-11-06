import http.client
import json
import threading
import unittest
from unittest import mock

import rdum
from rdum import controller
from rdum.web import DeviceServer


class CommandTests(unittest.TestCase):
    def test_commands_and_model_compatibility(self):
        examples = (
            ('next_screen', True, 'UM24C', b'\xf1'),
            ('rotate_screen', True, 'UM25C', b'\xf2'),
            ('next_data_group', True, 'UM24C', b'\xf3'),
            ('previous_screen', True, 'UM34C', b'\xf3'),
            ('clear_data_group', True, 'UM24C', b'\xf4'),
            ('set_data_group', 9, 'UM25C', b'\xa9'),
            ('set_record_threshold', 0.29, 'UM34C', b'\xcd'),
            ('set_screen_brightness', 0, 'UM24C', b'\xd0'),
            ('set_screen_timeout', 9, 'UM24C', b'\xe9'),
        )
        for name, value, model, expected in examples:
            with self.subTest(name=name):
                self.assertEqual(controller.command_bytes(name, value, model), expected)
        for name, value, model in (
            ('next_data_group', True, 'UM25C'),
            ('previous_screen', True, 'UM24C'),
            ('set_data_group', 0, 'UM24C'),
            ('set_record_threshold', 0.301, 'UM24C'),
            ('set_record_threshold', float('nan'), 'UM24C'),
            ('set_screen_brightness', True, 'UM24C'),
            ('set_screen_timeout', 10, 'UM24C'),
            ('rotate_screen', False, 'UM24C'),
            ('missing', True, 'UM24C'),
        ):
            with self.subTest(name=name, value=value, model=model):
                with self.assertRaises(ValueError):
                    controller.command_bytes(name, value, model)


class WebTests(unittest.TestCase):
    def setUp(self):
        self.device = mock.Mock()
        response = rdum.Response(device_type='UM25C')
        response.volts = 5.123
        response.amps = 0.1234
        self.device.recv.return_value = response.dump()
        self.server = DeviceServer(('127.0.0.1', 0), self.device, 'UM25C')
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.origin = 'http://127.0.0.1:{}'.format(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def post(self, payload, origin=None):
        return self.request('POST', '/api/command', json.dumps(payload), {
            'Content-Type': 'application/json',
            'Origin': origin if origin is not None else self.origin,
        })

    def test_status_uses_shared_protocol_and_scaling(self):
        status, body = self.request('GET', '/api/status')
        result = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(result['device_type'], 'UM25C')
        self.assertEqual(result['measurements']['volts'], 5.123)
        self.assertEqual(result['measurements']['amps'], 0.1234)
        self.assertEqual(len(result['measurements']['data_groups']), 10)
        self.device.send.assert_called_once_with(b'\xf0')

    def test_static_assets_and_unknown_route(self):
        for path, snippet in (('/', b'RDUM meter'), ('/app.js', b'/api/status'),
                              ('/style.css', b'.grid')):
            with self.subTest(path=path):
                status, body = self.request('GET', path)
                self.assertEqual(status, 200)
                self.assertIn(snippet, body)
        self.assertEqual(self.request('GET', '/unknown')[0], 404)

    def test_command_and_validation(self):
        with mock.patch('rdum.controller.time.sleep'):
            status, body = self.post({'command': 'set_data_group', 'value': 3})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)['ok'])
        self.device.send.assert_called_once_with(b'\xa3')
        self.device.send.reset_mock()
        for payload in (
            {'command': 'next_data_group', 'value': True},
            {'command': 'set_data_group', 'value': 10},
            {'command': 'set_data_group', 'value': False},
            {'command': 'next_screen'},
            {'command': [], 'value': True},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.post(payload)[0], 400)
        self.device.send.assert_not_called()

    def test_origin_host_and_content_type_are_checked(self):
        payload = {'command': 'clear_data_group', 'value': True}
        self.assertEqual(self.post(payload, 'http://evil.example')[0], 403)
        self.assertEqual(self.request('POST', '/api/command', json.dumps(payload),
                                      {'Content-Type': 'application/json'})[0], 403)
        self.assertEqual(self.request('GET', '/api/status', headers={'Host': 'evil.example'})[0], 400)
        self.assertEqual(self.request('POST', '/api/command', '{}',
                                      {'Origin': self.origin, 'Content-Type': 'text/plain'})[0], 415)
        self.device.send.assert_not_called()

    def test_device_operations_do_not_interleave(self):
        reading = threading.Event()
        release = threading.Event()

        def recv():
            reading.set()
            if not release.wait(5):
                raise TimeoutError('Test did not release the read')
            return rdum.Response(device_type='UM25C').dump()

        self.device.recv.side_effect = recv
        read_thread = threading.Thread(target=lambda: self.request('GET', '/api/status'))
        command_thread = threading.Thread(
            target=lambda: self.post({'command': 'next_screen', 'value': True}))
        with mock.patch('rdum.controller.time.sleep'):
            try:
                read_thread.start()
                self.assertTrue(reading.wait(5))
                command_thread.start()
                command_thread.join(0.1)
                self.assertTrue(command_thread.is_alive())
                self.device.send.assert_called_once_with(b'\xf0')
            finally:
                release.set()
                read_thread.join(5)
                if command_thread.ident is not None:
                    command_thread.join(5)
        self.assertFalse(read_thread.is_alive())
        self.assertFalse(command_thread.is_alive())
        self.assertEqual(self.device.send.call_args_list, [mock.call(b'\xf0'), mock.call(b'\xf1')])

    def test_device_failures_are_reported(self):
        self.device.recv.side_effect = OSError('disconnected')
        with self.assertLogs(level='ERROR'):
            status, body = self.request('GET', '/api/status')
        self.assertEqual(status, 502)
        self.assertIn('disconnected', json.loads(body)['error'])
        self.device.send.side_effect = OSError('write failed')
        with self.assertLogs(level='ERROR'):
            status, body = self.post({'command': 'next_screen', 'value': True})
        self.assertEqual(status, 502)
        self.assertIn('write failed', json.loads(body)['error'])


if __name__ == '__main__':
    unittest.main()
