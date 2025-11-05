# Copyright 2020-present PlatformIO <contact@platformio.org>
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
ESP-IDF Framework with Pre-compiled Libraries

Simplified version that uses pre-compiled ESP-IDF libraries instead of
building them through CMAKE.
"""

import os
from os.path import isdir, join, isfile

from SCons.Script import DefaultEnvironment

env = DefaultEnvironment()
platform = env.PioPlatform()
board = env.BoardConfig()

FRAMEWORK_DIR = platform.get_dir()
BUILD_DIR = env.subst("$BUILD_DIR")
PROJECT_DIR = env.subst("$PROJECT_DIR")

# Paths to pre-compiled ESP-IDF libraries
PREBUILT_DIR = join(FRAMEWORK_DIR, "prebuilt")
PREBUILT_LIB = join(PREBUILT_DIR, "liburack_espidf.a")
PREBUILT_INCLUDE = join(PREBUILT_DIR, "include")

# ESP-IDF headers location
ESPIDF_HEADERS = join(PREBUILT_INCLUDE, "esp-idf", "esp32")

print("Using pre-compiled ESP-IDF from: %s" % PREBUILT_DIR)

#
# Collect all ESP-IDF include directories
#

def get_espidf_includes():
    """Recursively collect all include directories from prebuilt ESP-IDF"""
    includes = []
    
    if not os.path.isdir(ESPIDF_HEADERS):
        print("Warning: ESP-IDF headers not found at: %s" % ESPIDF_HEADERS)
        return includes
    
    # Add main sdkconfig.h location
    includes.append(PREBUILT_INCLUDE)
    
    # Walk through all ESP-IDF components
    for component in os.listdir(ESPIDF_HEADERS):
        component_path = join(ESPIDF_HEADERS, component)
        if not os.path.isdir(component_path):
            continue
            
        # Add standard include directories
        for inc_dir in ["include", "platform_include", "include_bt"]:
            inc_path = join(component_path, inc_dir)
            if os.path.isdir(inc_path):
                includes.append(inc_path)
        
        # Add register directories for soc component
        if component == "soc":
            for item in os.listdir(component_path):
                item_path = join(component_path, item)
                if os.path.isdir(item_path):
                    register_path = join(item_path, "register")
                    if os.path.isdir(register_path):
                        includes.append(register_path)
                        # Also add register/soc subdirectory
                        register_soc_path = join(register_path, "soc")
                        if os.path.isdir(register_soc_path):
                            includes.append(register_soc_path)
    
    return includes

#
# Configure build environment
#

env.Replace(
    SIZEPROGREGEXP=r"^(?:\.iram0\.text|\.iram0\.vectors|\.dram0\.data|\.flash\.text|\.flash\.rodata|)\s+(\d+).*",
    SIZEDATAREGEXP=r"^(?:\.dram0\.data|\.dram0\.bss|\.noinit)\s+(\d+).*",
)

env.Append(
    ASFLAGS=["-x", "assembler-with-cpp"],

    CCFLAGS=[
        "-mlongcalls",
        "-Wno-frame-address",
        "-ffunction-sections",
        "-fdata-sections",
        "-Wno-error=unused-function",
        "-Wno-error=unused-variable",
        "-Wno-error=deprecated-declarations",
        "-Wno-unused-parameter",
        "-Wno-sign-compare",
        "-ggdb",
        "-Os",
        "-freorder-blocks",
        "-fstack-protector",
        "-fstrict-volatile-bitfields"
    ],

    CFLAGS=[
        "-std=gnu99",
        "-Wno-old-style-declaration"
    ],

    CXXFLAGS=[
        "-std=gnu++11",
        "-fexceptions",
        "-fno-rtti"
    ],

    CPPDEFINES=[
        "ESP32",
        "ESP_PLATFORM",
        ("F_CPU", "$BOARD_F_CPU"),
        "HAVE_CONFIG_H",
        ("MBEDTLS_CONFIG_FILE", '\\"mbedtls/esp_config.h\\"'),
        ("IDF_VER", '\\"v5.1.4-698-g96de2fbde7\\"'),
        "ARDUINO_ARCH_ESP32",
    ],

    CPPPATH=get_espidf_includes(),

    LINKFLAGS=[
        "-mlongcalls",
        "-Wl,--cref",
        "-Wl,--gc-sections",
        "-fno-rtti",
        "-fno-lto",
        "-Wl,--wrap=longjmp",
        "-Wl,--undefined=uxTopUsedPriority",
        "-T", "esp32_out.ld",
        "-T", "esp32.project.ld",
        "-T", "esp32.rom.ld",
        "-T", "esp32.rom.api.ld",
        "-T", "esp32.rom.libgcc.ld",
        "-T", "esp32.rom.newlib-data.ld",
        "-T", "esp32.rom.syscalls.ld",
        "-T", "esp32.peripherals.ld",
        "-u", "esp_app_desc",
        "-u", "pthread_include_pthread_impl",
        "-u", "pthread_include_pthread_cond_impl",
        "-u", "pthread_include_pthread_local_storage_impl",
        "-u", "pthread_include_pthread_rwlock_impl",
        "-u", "include_esp_phy_override",
        "-u", "ld_include_highint_hdl",
        "-u", "start_app",
        "-u", "start_app_other_cores",
        "-u", "__ubsan_include",
        "-Wl,-Map=%s" % join(BUILD_DIR, "firmware.map")
    ],

    LIBS=["gcc", "stdc++", "m", "c"],

    LIBPATH=[
        join(PREBUILT_DIR, "ld"),
    ],
)

# Add pre-compiled ESP-IDF library
if os.path.isfile(PREBUILT_LIB):
    env.Prepend(LIBS=["urack_espidf"])
    env.Append(LIBPATH=[PREBUILT_DIR])
else:
    print("Warning: Pre-compiled library not found at: %s" % PREBUILT_LIB)
    print("Please run the library builder script first.")
