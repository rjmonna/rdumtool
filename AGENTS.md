# Repository guide

## Build, test, and documentation

- `make` or `make build` builds a wheel with `python3 -m pip wheel`.
- `make test` runs `python3 -Wd -m unittest discover -v`; individual tests can be run with `python3 -m unittest tests.test_device`.
- VS Code debugging uses `.vscode/launch.json` (`RDUM web (Bluetooth)`, `RDUM web (serial)`, `Python: Debug web tests`); the Bluetooth address defaults to the maintainer's meter, which advertises as `E-test`, so automatic discovery cannot find it and `--bluetooth-device` is required.
- No lint target or linter configuration is present.
- `make doc` regenerates the plain-text `README` from `README.md` using Pandoc. `README.md` is the editable source; do not hand-edit the generated `README`.

## Architecture

`rdum/device.py` contains the device-facing layer: Bluetooth and serial transport classes, charging-mode constants, and `Response`, which decodes and encodes the device's 130-byte data packet. These are re-exported by `rdum/__init__.py` for compatibility. `rdum/controller.py` shares command validation, status reads, and JSON serialization between `rdum/tool.py` (the CLI) and `rdum/web.py` (the local web server). Web assets live in `rdum/webfiles/`. The top-level `rdumtool` launcher and console-script entry point both invoke `rdum.tool.main`.

The CLI supports UM24C, UM25C, and UM34C. Device-specific response markers and command compatibility are handled explicitly in the protocol and CLI layers; the README notes that UM24C is tested while UM25C and UM34C are not.

## Repository-specific conventions

- Keep packet layout, big-endian field decoding/encoding, unit conversions, and response labels centralized in `Response._std_defs` and `Response`; keep transport I/O in `DeviceBluetooth` and `DeviceSerial`.
- When changing device commands, preserve the per-model compatibility checks in `rdum.controller`. The command byte values and model support differ, even where command-line options are shared.
- UM25C voltage/current values use a different scale, represented by `Response.device_multiplier`; preserve that distinction when changing measurement conversion.
- `rdum/__init__.py` is also the source of `__version__`, which the package metadata reads.
- The package requires Python 3.10 or later; keep syntax and APIs compatible with that minimum.
