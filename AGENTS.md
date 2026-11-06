# Repository guide

## Build, test, and documentation

- `make` or `make build` builds a wheel with `python3 -m pip wheel`.
- `make test` runs `python3 -Wd -m unittest discover -v`; individual tests can be run with `python3 -m unittest tests.test_device`.
- No lint target or linter configuration is present.
- `make doc` regenerates the plain-text `README` from `README.md` using Pandoc. `README.md` is the editable source; do not hand-edit the generated `README`.

## Architecture

`rdum/__init__.py` contains the device-facing layer: Bluetooth and serial transport classes, charging-mode constants, and `Response`, which decodes and encodes the device's 130-byte data packet. `rdum/tool.py` is the CLI and application layer: it parses options, selects a transport, sends device commands, reads responses, and formats human-readable or JSON output. The top-level `rdumtool` launcher and the `setup.py` console-script entry point both invoke `rdum.tool.main`.

The CLI supports UM24C, UM25C, and UM34C. Device-specific response markers and command compatibility are handled explicitly in the protocol and CLI layers; the README notes that UM24C is tested while UM25C and UM34C are not.

## Repository-specific conventions

- Keep packet layout, big-endian field decoding/encoding, unit conversions, and response labels centralized in `Response._std_defs` and `Response`; keep transport I/O in `DeviceBluetooth` and `DeviceSerial`.
- When changing device commands, preserve the per-model compatibility checks in `RDUMTool.send_commands`. The command byte values and model support differ, even where command-line options are shared.
- UM25C voltage/current values use a different scale, represented by `Response.device_multiplier`; preserve that distinction when changing measurement conversion.
- `rdum/__init__.py` is also the source of `__version__`, which `setup.py` reads for package metadata.
- The package requires Python 3.10 or later; keep syntax and APIs compatible with that minimum.
