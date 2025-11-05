# Copyright 2014-present PlatformIO <contact@platformio.org>
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
Arduino

Arduino Wiring-based Framework allows writing cross-platform software to
control devices attached to a wide range of Arduino boards to create all
kinds of creative coding, interactive objects, spaces or physical experiences.

http://arduino.cc/en/Reference/HomePage
"""

# Extends: https://github.com/pioarduino/platform-espressif32/blob/develop/builder/main.py

import sys
from os.path import abspath, basename, isdir, isfile, join
from copy import deepcopy
from SCons.Script import DefaultEnvironment, SConscript

IS_WINDOWS = sys.platform.startswith("win")

env = DefaultEnvironment()
platform = env.PioPlatform()
board_config = env.BoardConfig()
build_mcu = board_config.get("build.mcu", "").lower()
partitions_name = board_config.get("build.partitions", board_config.get("build.arduino.partitions", ""))

# Use prebuilt directories instead of real packages
PREBUILT_DIR = join(platform.get_dir(), "prebuilt")
FRAMEWORK_DIR = join(PREBUILT_DIR, "include", "arduino")
FRAMEWORK_LIBS_DIR = join(PREBUILT_DIR, "include", "esp-idf")
assert isdir(PREBUILT_DIR)


#
# Helpers
#


def get_partition_table_csv(variants_dir):
    """Get partition table CSV - use prebuilt/default.csv or custom from variant"""
    variant_partitions_dir = join(variants_dir, board_config.get("build.variant", ""))

    if partitions_name:
        # A custom partitions file is selected
        if isfile(env.subst(join(variant_partitions_dir, partitions_name))):
            return join(variant_partitions_dir, partitions_name)

        # Check if it's an absolute path
        if isfile(env.subst(partitions_name)):
            return abspath(partitions_name)
        
        # Try in prebuilt directory
        prebuilt_csv = join(PREBUILT_DIR, partitions_name)
        if isfile(env.subst(prebuilt_csv)):
            return prebuilt_csv

    # Check for variant-specific partitions
    variant_partitions = join(variant_partitions_dir, "partitions.csv")
    if isfile(env.subst(variant_partitions)):
        return variant_partitions
    
    # Use default from prebuilt
    return join(PREBUILT_DIR, "default.csv")


def get_bootloader_image(variants_dir):
    """Get bootloader image path - use pre-compiled from prebuilt or custom from variant"""
    bootloader_image_file = "bootloader.bin"
    if partitions_name.endswith("tinyuf2.csv"):
        bootloader_image_file = "bootloader-tinyuf2.bin"

    # Check if variant has a custom bootloader
    variant_bootloader = join(
        variants_dir,
        board_config.get("build.variant", ""),
        board_config.get("build.arduino.custom_bootloader", bootloader_image_file),
    )
    
    if isfile(env.subst(variant_bootloader)):
        return variant_bootloader
    
    # Use pre-compiled bootloader from prebuilt directory
    return join(PREBUILT_DIR, "bootloader.bin")


def add_tinyuf2_extra_image():
    tinuf2_image = board_config.get(
        "upload.arduino.tinyuf2_image",
        join(variants_dir, board_config.get("build.variant", ""), "tinyuf2.bin"),
    )

    # Add the UF2 image only if it exists and it's not already added
    if not isfile(env.subst(tinuf2_image)):
        print("Warning! The `%s` UF2 bootloader image doesn't exist" % env.subst(tinuf2_image))
        return

    if any("tinyuf2.bin" == basename(extra_image[1]) for extra_image in env.get("FLASH_EXTRA_IMAGES", [])):
        print("Warning! An extra UF2 bootloader image is already added!")
        return

    env.Append(
        FLASH_EXTRA_IMAGES=[
            (
                board_config.get(
                    "upload.arduino.uf2_bootloader_offset",
                    ("0x2d0000" if env.subst("$BOARD").startswith("adafruit") else "0x410000"),
                ),
                tinuf2_image,
            ),
        ]
    )


#
# Run target-specific script to populate the environment with proper build flags
#

SConscript(
    join(
        FRAMEWORK_LIBS_DIR,
        build_mcu,
        "pioarduino-build.py",
    )
)

#
# Additional flags specific to Arduino core (not based on IDF)
#

env.Append(
    CFLAGS=["-Werror=return-type"],
    CXXFLAGS=["-Werror=return-type"],
)

#
# Target: Use Pre-compiled Library (instead of building core)
#

# We don't build Arduino core - it's already pre-compiled in liburack_arduino.a
# Just make sure variant path is available for includes
variants_dir = join(FRAMEWORK_DIR, "variants")

if "build.variants_dir" in board_config:
    variants_dir = join("$PROJECT_DIR", board_config.get("build.variants_dir"))

if "build.variant" in board_config:
    env.Append(CPPPATH=[join(variants_dir, board_config.get("build.variant"))])

# Pre-compiled library is added by arduino.py framework script
# No need to compile Arduino core here

#
# Process framework extra images
#

bootloader_image = get_bootloader_image(variants_dir)
flash_extra_images = [
    (
        "0x1000" if build_mcu in ["esp32", "esp32s2"] else ("0x2000" if build_mcu in ["esp32p4"] else "0x0000"),
        bootloader_image,
    ),
    ("0x8000", join(env.subst("$BUILD_DIR"), "partitions.bin")),
    ("0xe000", join(PREBUILT_DIR, "boot_app0.bin")),
] + [(offset, join(FRAMEWORK_DIR, img)) for offset, img in board_config.get("upload.arduino.flash_extra_images", [])]

print(f"URack: Setting up FLASH_EXTRA_IMAGES with {len(flash_extra_images)} files:")
for offset, path in flash_extra_images:
    print(f"  {offset} -> {path}")

env.Append(
    LIBSOURCE_DIRS=[join(FRAMEWORK_DIR, "libraries")],
    FLASH_EXTRA_IMAGES=flash_extra_images,
)

# Add an extra UF2 image if the 'TinyUF2' partition is selected
if partitions_name.endswith("tinyuf2.csv") or board_config.get("upload.arduino.tinyuf2_image", ""):
    add_tinyuf2_extra_image()

#
# Copy pre-compiled partition table
#

# Use pre-compiled partitions.bin from prebuilt directory
prebuilt_partitions = join(PREBUILT_DIR, "partitions.bin")
build_partitions = join("$BUILD_DIR", "partitions.bin")

# Copy partitions.bin from prebuilt to build directory
if IS_WINDOWS:
    copy_cmd = "copy /Y"
else:
    copy_cmd = "cp"
    
partition_table = env.Command(
    build_partitions,
    prebuilt_partitions,
    env.VerboseAction(
        "%s \"$SOURCE\" \"$TARGET\"" % copy_cmd,
        "Copying partitions $TARGET",
    ),
)
env.Depends("$BUILD_DIR/$PROGNAME$PROGSUFFIX", partition_table)

#
#  Adjust the `esptoolpy` command in the `ElfToBin` builder with firmware checksum offset
#

action = deepcopy(env["BUILDERS"]["ElfToBin"].action)
action.cmd_list = env["BUILDERS"]["ElfToBin"].action.cmd_list.replace("-o", "--elf-sha256-offset 0xb0 -o")
env["BUILDERS"]["ElfToBin"].action = action

#
# Set application offset for upload
#

env.Replace(
    ESP32_APP_OFFSET=board_config.get("upload.offset_address", "0x10000")
)
