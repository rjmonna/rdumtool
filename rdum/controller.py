"""Shared device operations for the command-line and web interfaces."""

import datetime
import time

from .device import Response


MODELS = ('UM24C', 'UM25C', 'UM34C')
COMMANDS = {
    'next_screen': (b'\xf1', MODELS),
    'rotate_screen': (b'\xf2', MODELS),
    'next_data_group': (b'\xf3', ('UM24C',)),
    'previous_screen': (b'\xf3', ('UM25C', 'UM34C')),
    'clear_data_group': (b'\xf4', MODELS),
    'set_data_group': (lambda x: bytes([0xa0 + x]), ('UM25C', 'UM34C')),
    'set_record_threshold': (lambda x: bytes([0xb0 + round(x * 100)]), MODELS),
    'set_screen_brightness': (lambda x: bytes([0xd0 + x]), MODELS),
    'set_screen_timeout': (lambda x: bytes([0xe0 + x]), MODELS),
}


def command_bytes(name, value, device_type):
    if name not in COMMANDS:
        raise ValueError('Unknown command')
    command, models = COMMANDS[name]
    if device_type not in models:
        raise ValueError('{} not supported on this device'.format(name))
    if isinstance(command, bytes):
        if value is not True:
            raise ValueError('Command value must be true')
        return command
    if name == 'set_record_threshold':
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not 0 <= value <= 0.30 or round(value * 100) / 100 != value):
            raise ValueError('Threshold must be 0.00 to 0.30 in 0.01 A steps')
    else:
        maximum = 5 if name == 'set_screen_brightness' else 9
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
            raise ValueError('Command value must be an integer from 0 to {}'.format(maximum))
    return command(value)


def send_command(device, name, value, device_type):
    device.send(command_bytes(name, value, device_type))
    time.sleep(0.5)


def read_response(device, device_type):
    device.send(b'\xf0')
    return Response(device.recv(), collection_time=datetime.datetime.now(), device_type=device_type)


def response_dict(response):
    result = {name: getattr(response, name) for name in response.labels}
    result['data_groups'] = [
        {'amp_hours': group.amp_hours, 'watt_hours': group.watt_hours}
        for group in response.data_groups
    ]
    result['collection_time'] = response.collection_time.timestamp()
    return result
