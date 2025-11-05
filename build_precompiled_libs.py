#!/usr/bin/env python3
# Copyright 2024-present URack Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Script to build pre-compiled libraries for URack ESP32 Platform

This script:
1. Creates a temporary build environment
2. Compiles ESP-IDF and Arduino framework
3. Compiles required libraries (Adafruit GFX, SSD1306, ESP32Encoder, NeoPixel, MIDI)
4. Combines everything into static libraries
5. Exports headers
"""

import os
import sys
import shutil
import subprocess
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
PREBUILT_DIR = SCRIPT_DIR / "prebuilt"
BUILD_TEMP_DIR = SCRIPT_DIR / "build_temp"
PLATFORM_DIR = SCRIPT_DIR / "platform-espressif32-54.03.20-esp"

# Libraries to include
LIBRARIES = [
    "adafruit/Adafruit GFX Library@^1.11.9",
    "adafruit/Adafruit SSD1306@^2.5.7",
    "madhephaestus/ESP32Encoder@^0.11.7",
    "adafruit/Adafruit NeoPixel@^1.12.0",
    "fortyseveneffects/MIDI Library@^5.0.2"
]

def run_command(cmd, cwd=None):
    """Run a command and return output"""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result.stdout

def create_temp_project():
    """Create a temporary PlatformIO project for building"""
    print("Creating temporary build project...")
    
    # Clean and create temp directory
    if BUILD_TEMP_DIR.exists():
        shutil.rmtree(BUILD_TEMP_DIR)
    BUILD_TEMP_DIR.mkdir(parents=True)
    
    # Create project structure - PlatformIO requires src/ with at least one .cpp file
    # Arduino framework needs setup()/loop() to be defined to compile its main.cpp with app_main
    (BUILD_TEMP_DIR / "src").mkdir()
    (BUILD_TEMP_DIR / "include").mkdir()
    
    # Minimal user code - Arduino's main.cpp (with app_main) will be compiled in FrameworkArduino/
    # This file will be EXCLUDED from library (all src/* is excluded)
    user_main = BUILD_TEMP_DIR / "src" / "user.cpp"
    with open(user_main, "w") as f:
        f.write("""#include <Arduino.h>
void setup() {}
void loop() {}
""")
    
    # Create platformio.ini
    platformio_ini = BUILD_TEMP_DIR / "platformio.ini"
    with open(platformio_ini, "w") as f:
        f.write(f"""[env:esp32dev]
platform = file://{PLATFORM_DIR}
board = esp32dev
framework = arduino
monitor_speed = 115200
lib_deps =
""")
        for lib in LIBRARIES:
            f.write(f"    {lib}\n")

def copy_headers_only(src_dir, dest_dir, extensions=('.h', '.hpp', '.inc')):
    """
    Recursively copy only header files from src_dir to dest_dir,
    preserving directory structure but excluding source files (.c, .cpp, .S).
    """
    if not src_dir.exists():
        return
    
    for item in src_dir.rglob('*'):
        if item.is_file() and item.suffix in extensions:
            relative_path = item.relative_to(src_dir)
            dest_file = dest_dir / relative_path
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest_file)

def build_project():
    """Build the temporary project"""
    print("Building project...")
    run_command(["pio", "run"], cwd=BUILD_TEMP_DIR)

def collect_objects():
    """Collect all object files from the build"""
    print("Collecting object files...")
    
    build_dir = BUILD_TEMP_DIR / ".pio" / "build" / "esp32dev"
    
    if not build_dir.exists():
        print(f"Error: Build directory not found: {build_dir}")
        sys.exit(1)
    
    # Find all .o files
    obj_files = list(build_dir.rglob("*.o"))
    
    # Exclude ALL files from src/ directory (ProjectSrc) - this is user code, not library code
    # Keep only framework and library object files
    obj_files = [f for f in obj_files if "src" not in str(f.relative_to(build_dir))]
    
    print(f"Found {len(obj_files)} object files (after excluding src/)")
    
    # Debug: show what we're including
    framework_objs = [f for f in obj_files if "FrameworkArduino" in str(f)]
    print(f"  Framework objects: {len(framework_objs)}")
    if framework_objs:
        main_obj = [f for f in framework_objs if "main.cpp.o" in str(f)]
        if main_obj:
            print(f"  ✅ Including FrameworkArduino/main.cpp.o with app_main")
        else:
            print(f"  ⚠️  WARNING: FrameworkArduino/main.cpp.o not found!")
    
    return obj_files

def create_static_library(obj_files, output_lib):
    """Create static library from object files"""
    print(f"Creating static library: {output_lib}")
    
    # Find ar tool
    ar_tool = shutil.which("xtensa-esp32-elf-ar")
    if not ar_tool:
        # Try to find it in PlatformIO packages
        home = Path.home()
        ar_candidates = list((home / ".platformio" / "packages").rglob("xtensa-esp32-elf-ar*"))
        if ar_candidates:
            ar_tool = str(ar_candidates[0])
        else:
            print("Error: xtensa-esp32-elf-ar not found")
            sys.exit(1)
    
    # Create library
    output_lib.parent.mkdir(parents=True, exist_ok=True)
    
    # Create library in chunks (to avoid command line length limits)
    chunk_size = 50
    obj_chunks = [obj_files[i:i + chunk_size] for i in range(0, len(obj_files), chunk_size)]
    
    # Create initial library with first chunk
    if obj_chunks:
        cmd = [ar_tool, "rcs", str(output_lib)] + [str(f) for f in obj_chunks[0]]
        run_command(cmd)
        
        # Add remaining chunks
        for chunk in obj_chunks[1:]:
            cmd = [ar_tool, "rs", str(output_lib)] + [str(f) for f in chunk]
            run_command(cmd)
    
    print(f"Library created: {output_lib}")

def collect_headers():
    """Collect all necessary headers"""
    print("Collecting headers...")
    
    include_dir = PREBUILT_DIR / "include"
    if include_dir.exists():
        shutil.rmtree(include_dir)
    include_dir.mkdir(parents=True)
    
    # Get libdeps directory
    libdeps_dir = BUILD_TEMP_DIR / ".pio" / "libdeps" / "esp32dev"
    
    if not libdeps_dir.exists():
        print(f"Warning: libdeps directory not found: {libdeps_dir}")
        return
    
    # Copy library headers
    libraries_include = include_dir / "libraries"
    libraries_include.mkdir(exist_ok=True)
    
    # Copy each library's headers
    library_mapping = {
        "Adafruit GFX Library": "Adafruit_GFX_Library",
        "Adafruit SSD1306": "Adafruit_SSD1306",
        "ESP32Encoder": "ESP32Encoder",
        "Adafruit NeoPixel": "Adafruit_NeoPixel",
        "MIDI Library": "MIDI_Library"
    }
    
    for lib_dir in libdeps_dir.iterdir():
        if lib_dir.is_dir() and lib_dir.name != "integrity.dat":
            lib_name = lib_dir.name
            # Match library - exact match now
            if lib_name in library_mapping:
                mapped_name = library_mapping[lib_name]
                dest_dir = libraries_include / mapped_name
                dest_dir.mkdir(exist_ok=True, parents=True)
                
                # Copy only header files
                if (lib_dir / "src").exists():
                    copy_headers_only(lib_dir / "src", dest_dir)
                    print(f"Copied headers for {lib_name} (from src/)")
                elif (lib_dir / "include").exists():
                    copy_headers_only(lib_dir / "include", dest_dir)
                    print(f"Copied headers for {lib_name} (from include/)")
                else:
                    copy_headers_only(lib_dir, dest_dir)
                    print(f"Copied headers for {lib_name} (from root)")
            elif lib_name == "Adafruit BusIO":
                # Also copy BusIO as it's a dependency of Adafruit libraries
                dest_dir = libraries_include / "Adafruit_BusIO"
                dest_dir.mkdir(exist_ok=True, parents=True)
                
                # Copy only header files
                if (lib_dir / "src").exists():
                    copy_headers_only(lib_dir / "src", dest_dir)
                elif (lib_dir / "include").exists():
                    copy_headers_only(lib_dir / "include", dest_dir)
                print(f"Copied headers for Adafruit BusIO")
    
    # Try to copy Arduino and ESP-IDF headers from framework packages
    pio_packages = Path.home() / ".platformio" / "packages"
    
    # Copy Arduino core headers (only .h/.hpp files)
    arduino_src = pio_packages / "framework-arduinoespressif32"
    if arduino_src.exists():
        arduino_dest = include_dir / "arduino"
        arduino_dest.mkdir(exist_ok=True, parents=True)
        
        # Copy cores (only headers)
        if (arduino_src / "cores").exists():
            copy_headers_only(arduino_src / "cores", arduino_dest / "cores")
        
        # Copy variants (only headers)
        if (arduino_src / "variants").exists():
            copy_headers_only(arduino_src / "variants", arduino_dest / "variants")
        
        # Copy built-in libraries (only headers)
        if (arduino_src / "libraries").exists():
            copy_headers_only(arduino_src / "libraries", arduino_dest / "libraries")
        
        # Copy tools directory selectively (only scripts and data, no binaries)
        if (arduino_src / "tools").exists():
            tools_src = arduino_src / "tools"
            tools_dest = arduino_dest / "tools"
            tools_dest.mkdir(exist_ok=True, parents=True)
            
            # Copy only necessary file types (exclude .exe and other binaries)
            allowed_extensions = ('.py', '.csv', '.ld', '.json', '.txt', '.md')
            
            for item in tools_src.rglob('*'):
                if item.is_file():
                    # Skip binary executables
                    if item.suffix.lower() in ('.exe', '.dll', '.so', '.dylib', '.bin'):
                        continue
                    # Copy only allowed extensions or files without extension
                    if item.suffix in allowed_extensions or not item.suffix:
                        relative_path = item.relative_to(tools_src)
                        dest_file = tools_dest / relative_path
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, dest_file)
        
        print("Copied Arduino core headers")
    
    # Copy Arduino-ESP32 library headers (ESP-IDF components)
    arduino_libs_src = pio_packages / "framework-arduinoespressif32-libs"
    if arduino_libs_src.exists():
        espidf_dest = include_dir / "esp-idf"
        espidf_dest.mkdir(exist_ok=True)
        
        # Copy ESP32 specific headers - preserve the esp32/include structure
        esp32_dir = arduino_libs_src / "esp32"
        if esp32_dir.exists():
            # Copy entire esp32 directory structure including lib/ 
            # lib/ contains ESP-IDF precompiled libraries (WiFi, BLE, crypto, etc.) needed for linking
            shutil.copytree(esp32_dir, espidf_dest / "esp32", dirs_exist_ok=True)
            
            # Now overwrite the pioarduino-build.py with adapted version
            adapted_script = espidf_dest / "esp32" / "pioarduino-build.py"
            if adapted_script.exists():
                content = adapted_script.read_text()
                # Replace package directory paths with prebuilt paths
                content = content.replace(
                    'FRAMEWORK_DIR = env.PioPlatform().get_package_dir("framework-arduinoespressif32")',
                    'PREBUILT_DIR = join(env.PioPlatform().get_dir(), "prebuilt")\nFRAMEWORK_DIR = join(PREBUILT_DIR, "include", "arduino")'
                )
                content = content.replace(
                    'FRAMEWORK_SDK_DIR = env.PioPlatform().get_package_dir(\n    "framework-arduinoespressif32-libs"\n)',
                    'FRAMEWORK_SDK_DIR = join(PREBUILT_DIR, "include", "esp-idf")'
                )
                # Replace Build Core Library section with pre-compiled library usage
                content = content.replace(
                    '# Target: Build Core Library',
                    '# Target: Use Pre-compiled Library (instead of building core)'
                )
                # Remove the core building code
                import re
                # Find and replace the section between "# Target: Build Core Library" and "# Process framework extra images"
                pattern = r'(# Target: Use Pre-compiled Library.*?\n#\n)(.*?)(#\n# Process framework extra images)'
                replacement = r'\1# We don\'t build Arduino core - it\'s already pre-compiled in liburack_arduino.a\n# Just make sure variant path is available for includes\nvariants_dir = join(FRAMEWORK_DIR, "variants")\n\nif "build.variants_dir" in board_config:\n    variants_dir = join("$PROJECT_DIR", board_config.get("build.variants_dir"))\n\nif "build.variant" in board_config:\n    env.Append(CPPPATH=[join(variants_dir, board_config.get("build.variant"))])\n\n# Pre-compiled library is added by arduino.py framework script\n# No need to compile Arduino core here\n\n\3'
                content = re.sub(pattern, replacement, content, flags=re.DOTALL)
                adapted_script.write_text(content)
                print("Adapted pioarduino-build.py in esp32 directory")
        
        print("Copied ESP-IDF headers from Arduino libs")
    
    # Copy ESP-IDF headers
    espidf_dirs = list(pio_packages.glob("framework-espidf*"))
    if espidf_dirs:
        espidf_src = espidf_dirs[0]
        espidf_dest = include_dir / "esp-idf"
        espidf_dest.mkdir(exist_ok=True)
        
        # Copy component headers
        components_dir = espidf_src / "components"
        if components_dir.exists():
            for component in components_dir.iterdir():
                if component.is_dir():
                    inc_dir = component / "include"
                    if inc_dir.exists():
                        dest = espidf_dest / component.name
                        shutil.copytree(inc_dir, dest, dirs_exist_ok=True)
        
        print("Copied ESP-IDF headers")
    
    # Copy linker scripts and sdkconfig.h
    ld_dir = PREBUILT_DIR / "ld"
    ld_dir.mkdir(parents=True, exist_ok=True)
    
    # Try to find linker scripts
    arduino_libs_pkg = pio_packages / "framework-arduinoespressif32-libs"
    if arduino_libs_pkg.exists():
        ld_src = arduino_libs_pkg / "esp32" / "ld"
        if ld_src.exists():
            for ld_file in ld_src.glob("*.ld"):
                shutil.copy2(ld_file, ld_dir)
            print("Copied linker scripts")
        
        # Copy sdkconfig.h to root of include
        sdkconfig_files = list((arduino_libs_pkg / "esp32").rglob("sdkconfig.h"))
        if sdkconfig_files:
            # Copy to multiple locations where it might be needed
            shutil.copy2(sdkconfig_files[0], include_dir / "sdkconfig.h")
            if espidf_dest.exists():
                shutil.copy2(sdkconfig_files[0], espidf_dest / "sdkconfig.h")
            print(f"Copied sdkconfig.h")

def main():
    print("=" * 60)
    print("URack ESP32 Pre-compiled Library Builder")
    print("=" * 60)
    
    # Step 1: Create temporary project
    create_temp_project()
    
    # Step 2: Build project
    build_project()
    
    # Step 3: Collect object files
    obj_files = collect_objects()
    
    # Step 4: Create static library
    output_lib = PREBUILT_DIR / "liburack_arduino.a"
    create_static_library(obj_files, output_lib)
    
    # Step 5: Collect headers
    collect_headers()
    
    print("\n" + "=" * 60)
    print("Build completed successfully!")
    print(f"Library: {output_lib}")
    print(f"Headers: {PREBUILT_DIR / 'include'}")
    print("=" * 60)
    
    # Optional: Clean up temp directory
    # if BUILD_TEMP_DIR.exists():
    #     shutil.rmtree(BUILD_TEMP_DIR)

if __name__ == "__main__":
    main()

