import datetime
import io
import json
import socket
import struct
import sys
import unittest
from unittest import mock

import rdum
from rdum.tool import RDUMTool, parse_args


class BluetoothTests(unittest.TestCase):
    def test_native_socket_preferred_when_pybluez_is_installed(self):
        connection = mock.Mock()
        bluetooth = mock.Mock()
        with mock.patch.dict(sys.modules, {'bluetooth': bluetooth}):
            with mock.patch.object(socket, 'AF_BLUETOOTH', 31, create=True):
                with mock.patch.object(socket, 'BTPROTO_RFCOMM', 3, create=True):
                    with mock.patch.object(socket, 'socket', return_value=connection):
                        rdum.DeviceBluetooth('00:11:22:33:44:55')
        bluetooth.BluetoothSocket.assert_not_called()
        connection.connect.assert_called_once_with(('00:11:22:33:44:55', 1))

    def test_native_socket_connect_send_and_fragmented_read(self):
        connection = mock.Mock()
        connection.recv.side_effect = [b'a' * 40, b'b' * 90]
        with mock.patch.dict(sys.modules, {'bluetooth': None}):
            with mock.patch.object(socket, 'AF_BLUETOOTH', 31, create=True):
                with mock.patch.object(socket, 'BTPROTO_RFCOMM', 3, create=True):
                    with mock.patch.object(socket, 'socket', return_value=connection):
                        device = rdum.DeviceBluetooth('00:11:22:33:44:55')
        connection.settimeout.assert_called_once_with(5)
        connection.connect.assert_called_once_with(('00:11:22:33:44:55', 1))
        device.send(b'\xf0')
        connection.sendall.assert_called_once_with(b'\xf0')
        self.assertEqual(device.recv(), b'a' * 40 + b'b' * 90)
        self.assertEqual(connection.recv.call_args_list, [mock.call(130), mock.call(90)])
        device.close()
        connection.close.assert_called_once_with()

    def test_disconnect_is_reported(self):
        device = rdum.DeviceBluetooth()
        device.dev = mock.Mock()
        device.dev.recv.side_effect = [b'abc', b'']
        with self.assertRaisesRegex(IOError, '3 of 130 bytes'):
            device.recv()

    def test_failed_connection_closes_socket(self):
        connection = mock.Mock()
        connection.connect.side_effect = OSError('connection failed')
        with mock.patch.dict(sys.modules, {'bluetooth': None}):
            with mock.patch.object(socket, 'AF_BLUETOOTH', 31, create=True):
                with mock.patch.object(socket, 'BTPROTO_RFCOMM', 3, create=True):
                    with mock.patch.object(socket, 'socket', return_value=connection):
                        with self.assertRaisesRegex(OSError, 'connection failed'):
                            rdum.DeviceBluetooth('00:11:22:33:44:55')
        connection.close.assert_called_once_with()

    def test_discovery_requires_pybluez(self):
        with mock.patch.dict(sys.modules, {'bluetooth': None}):
            device = rdum.DeviceBluetooth()
        with self.assertRaisesRegex(RuntimeError, 'requires PyBluez'):
            device.scan()


class SerialTests(unittest.TestCase):
    def test_fragmented_read_and_timeout(self):
        with mock.patch.dict(sys.modules, {'serial': mock.Mock()}):
            device = rdum.DeviceSerial()
        device.dev = mock.Mock()
        device.dev.read.side_effect = [b'a' * 40, b'b' * 90]
        self.assertEqual(device.recv(), b'a' * 40 + b'b' * 90)
        self.assertEqual(device.dev.read.call_args_list, [mock.call(130), mock.call(90)])
        device.dev.read.side_effect = [b'abc', b'']
        with self.assertRaisesRegex(IOError, '3 of 130 bytes'):
            device.recv()

    def test_short_write_is_reported(self):
        with mock.patch.dict(sys.modules, {'serial': mock.Mock()}):
            device = rdum.DeviceSerial()
        device.dev = mock.Mock()
        device.dev.write.return_value = 0
        with self.assertRaisesRegex(IOError, 'Incomplete serial write'):
            device.send(b'\xf0')


class ResponseTests(unittest.TestCase):
    def test_device_packet(self):
        packet = bytes.fromhex(
            '096301fa000000000000001400440000'
            '00000023000000000000000000000000'
            '00000000000000000000000000000000'
            '00000000000000000000000000000000'
            '00000000000000000000000000000000'
            '00000000000000000000000000000000'
            '00000000000000000000000000000000'
            '000000000000000100030001869f0000'
            'fff1'
        )
        response = rdum.Response(packet)
        self.assertEqual(response.volts, 5.06)
        self.assertEqual(response.amps, 0)
        self.assertEqual(response.temp_c, 20)
        self.assertEqual(response.data_groups[0].amp_hours, 0.035)
        self.assertEqual(response.dump(), packet)

    def test_scaled_fields_round_trip_without_float_truncation(self):
        for model in ('UM24C', 'UM25C', 'UM34C'):
            template = rdum.Response(device_type=model)
            for name in ('volts', 'amps', 'watts', 'data_line_positive_volts',
                         'data_line_negative_volts', 'record_amphours', 'record_watthours',
                         'record_threshold', 'resistance'):
                _, offset, size, _, _ = template._std_defs[name]
                for value in (29, 58, 253, 506, 1001):
                    with self.subTest(model=model, field=name, value=value):
                        packet = bytearray(template.dump())
                        packet[offset:offset + size] = value.to_bytes(size, 'big')
                        self.assertEqual(rdum.Response(bytes(packet), device_type=model).dump(), bytes(packet))

            for value in (29, 58, 253, 506, 1001):
                packet = bytearray(template.dump())
                packet[16:20] = struct.pack('>L', value)
                packet[20:24] = struct.pack('>L', value)
                self.assertEqual(rdum.Response(bytes(packet), device_type=model).dump(), bytes(packet))

    def test_shared_markers_have_model_specific_scales(self):
        original = rdum.Response(device_type='UM24C')
        original.volts = 5.07
        original.amps = 0.123
        packet = original.dump()
        um24 = rdum.Response(packet, device_type='UM24C')
        um25 = rdum.Response(packet, device_type='UM25C')
        self.assertAlmostEqual(um24.volts, 5.07)
        self.assertAlmostEqual(um24.amps, 0.123)
        self.assertAlmostEqual(um25.volts, 0.507)
        self.assertAlmostEqual(um25.amps, 0.0123)

    def test_invalid_packet_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Invalid data length'):
            rdum.Response(b'\x09\x63')
        with self.assertRaisesRegex(ValueError, 'Invalid start marker'):
            rdum.Response(b'\x00' * 130)


class CLITests(unittest.TestCase):
    def test_all_record_threshold_commands(self):
        tool = RDUMTool()
        tool.dev = mock.Mock()
        with mock.patch('rdum.tool.time.sleep'):
            for value in range(31):
                tool.args = parse_args(['rdumtool', '--set-record-threshold', str(value / 100)])
                tool.send_commands()
                tool.dev.send.assert_called_with(bytes([0xb0 + value]))
        self.assertEqual(tool.dev.send.call_count, 31)

    def test_json_collection_time_is_local_timestamp(self):
        tool = RDUMTool()
        timestamp = datetime.datetime(2020, 7, 1, 12, 0)
        response = rdum.Response(collection_time=timestamp)
        with mock.patch('sys.stdout', new_callable=io.StringIO) as output:
            tool.print_json(response)
        self.assertEqual(json.loads(output.getvalue())['collection_time'], timestamp.timestamp())

    def test_device_closed_after_failure(self):
        tool = RDUMTool()
        device = mock.Mock()
        tool.setup_device = mock.Mock(side_effect=lambda: setattr(tool, 'dev', device))
        tool.send_commands = mock.Mock()
        tool.loop = mock.Mock(side_effect=ValueError('bad packet'))
        with mock.patch('rdum.tool.parse_args', return_value=parse_args(['rdumtool'])):
            with self.assertRaisesRegex(ValueError, 'bad packet'):
                tool.main()
        device.close.assert_called_once_with()

    def test_unknown_charging_mode_is_displayed(self):
        tool = RDUMTool()
        tool.args = parse_args(['rdumtool'])
        response = rdum.Response()
        response.charging_mode = 42
        with mock.patch('sys.stdout', new_callable=io.StringIO) as output:
            tool.print_human(response)
        self.assertIn('Unknown (42)', output.getvalue())


if __name__ == '__main__':
    unittest.main()
