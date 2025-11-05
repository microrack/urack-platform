# URack ESP32 Platform

Custom PlatformIO platform for ESP32 with pre-compiled Arduino and ESP-IDF libraries.

## Features

- **Pre-compiled libraries**: Arduino framework and user libraries are pre-compiled into static library for faster builds
- **ESP32 support**: Full support for ESP32 microcontroller
- **Arduino framework**: Compatible with Arduino framework and libraries
- **Board support**: Custom board `mod-esp32-v1`
- **Library dependencies**: Includes pre-compiled:
  - Adafruit GFX Library
  - Adafruit SSD1306
  - ESP32Encoder
  - Adafruit NeoPixel
  - MIDI Library
  - Adafruit BusIO

## Structure

```
urack-platform/
├── boards/               # Board definitions
│   └── mod-esp32-v1.json
├── builder/              # Build scripts
│   ├── main.py          # Main platform builder
│   └── frameworks/      # Framework builders
│       ├── arduino.py   # Arduino framework
│       ├── espidf.py    # ESP-IDF framework  
│       └── pioarduino-build.py
├── prebuilt/             # Pre-compiled libraries and headers
│   ├── liburack_arduino.a    # Static library
│   ├── ld/              # Linker scripts
│   └── include/         # All headers (Arduino, ESP-IDF, libraries)
├── platform.json         # Platform configuration
├── platform.py          # Platform class
└── build_precompiled_libs.py  # Script to build prebuilt libraries

## Building Pre-compiled Libraries

To rebuild the pre-compiled libraries:

```bash
cd urack-platform
python3 build_precompiled_libs.py
```

This will:
1. Create a temporary PlatformIO project
2. Compile Arduino core and all dependency libraries
3. Archive all object files into `liburack_arduino.a`
4. Copy all necessary headers to `prebuilt/include/`
5. Copy linker scripts and bootloader files

## Usage

In your `platformio.ini`:

```ini
[env:modesp32v1]
platform = file://path/to/urack-platform
board = mod-esp32-v1
framework = arduino
monitor_speed = 115200
```

## How It Works

1. **Pre-compilation**: Core libraries are compiled once using the build script
2. **User code compilation**: Only user code (`src/` and `lib/`) is compiled during project builds
3. **Linking**: User object files are linked against the pre-compiled static library
4. **Headers**: All necessary headers are provided from `prebuilt/include/`

This approach significantly speeds up compilation times as the framework and libraries don't need to be recompiled for each project.

## Build Time Comparison

- **Traditional build** (first time): ~2-3 minutes
- **URack platform** (after prebuilt): ~12 seconds
- **Incremental builds**: <5 seconds

## Requirements

- PlatformIO Core >= 6.1.16
- Python 3.6+
- ESP32 toolchain (automatically installed by PlatformIO)

## License

Apache-2.0
