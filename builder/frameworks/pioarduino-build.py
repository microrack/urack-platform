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

from os.path import abspath, basename, isdir, isfile, join
from copy import deepcopy
from SCons.Script import DefaultEnvironment, SConscript

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
    fwpartitions_dir = join(FRAMEWORK_DIR, "tools", "partitions")
    variant_partitions_dir = join(variants_dir, board_config.get("build.variant", ""))

    if partitions_name:
        # A custom partitions file is selected
        if isfile(env.subst(join(variant_partitions_dir, partitions_name))):
            return join(variant_partitions_dir, partitions_name)

        return abspath(
            join(fwpartitions_dir, partitions_name)
            if isfile(env.subst(join(fwpartitions_dir, partitions_name)))
            else partitions_name
        )

    variant_partitions = join(variant_partitions_dir, "partitions.csv")
    return variant_partitions if isfile(env.subst(variant_partitions)) else join(fwpartitions_dir, "default.csv")


def get_bootloader_image(variants_dir):
    bootloader_image_file = "bootloader.bin"
    if partitions_name.endswith("tinyuf2.csv"):
        bootloader_image_file = "bootloader-tinyuf2.bin"

    variant_bootloader = join(
        variants_dir,
        board_config.get("build.variant", ""),
        board_config.get("build.arduino.custom_bootloader", bootloader_image_file),
    )

    # Get boot mode and frequency by calling the functions directly
    boot_mode = env["__get_board_boot_mode"](env) if "__get_board_boot_mode" in env else board_config.get("build.boot", board_config.get("build.flash_mode", "dio"))
    boot_freq = env["__get_board_f_boot"](env) if "__get_board_f_boot" in env else "40m"
    
    bootloader_elf = join(
        FRAMEWORK_LIBS_DIR,
        build_mcu,
        "bin",
        f"bootloader_{boot_mode}_{boot_freq}.elf",
    )
    
    return (
        variant_bootloader
        if isfile(env.subst(variant_bootloader))
        else generate_bootloader_image(bootloader_elf)
    )


def generate_bootloader_image(bootloader_elf):
    bootloader_cmd = env.Command(
        join("$BUILD_DIR", "bootloader.bin"),
        bootloader_elf,
        env.VerboseAction(
            " ".join(
                [
                    '"$PYTHONEXE" "$OBJCOPY"',
                    "--chip",
                    build_mcu,
                    "elf2image",
                    "--flash_mode",
                    "${__get_board_flash_mode(__env__)}",
                    "--flash_freq",
                    "${__get_board_f_image(__env__)}",
                    "--flash_size",
                    board_config.get("upload.flash_size", "4MB"),
                    "-o",
                    "$TARGET",
                    "$SOURCES",
                ]
            ),
            "Building $TARGET",
        ),
    )

    env.Depends("$BUILD_DIR/$PROGNAME$PROGSUFFIX", bootloader_cmd)

    # Because the Command always returns a NodeList, we have to
    # access the first element in the list to get the Node object
    # that actually represents the bootloader image.
    # Also, this file is later used in generic Python code, so the
    # Node object in converted to a generic string
    return str(bootloader_cmd[0])


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

env.Append(
    LIBSOURCE_DIRS=[join(FRAMEWORK_DIR, "libraries")],
    FLASH_EXTRA_IMAGES=[
        (
            "0x1000" if build_mcu in ["esp32", "esp32s2"] else ("0x2000" if build_mcu in ["esp32p4"] else "0x0000"),
            get_bootloader_image(variants_dir),
        ),
        ("0x8000", join(env.subst("$BUILD_DIR"), "partitions.bin")),
        ("0xe000", join(FRAMEWORK_DIR, "tools", "partitions", "boot_app0.bin")),
    ]
    + [(offset, join(FRAMEWORK_DIR, img)) for offset, img in board_config.get("upload.arduino.flash_extra_images", [])],
)

# Add an extra UF2 image if the 'TinyUF2' partition is selected
if partitions_name.endswith("tinyuf2.csv") or board_config.get("upload.arduino.tinyuf2_image", ""):
    add_tinyuf2_extra_image()

#
# Generate partition table
#

env.Replace(PARTITIONS_TABLE_CSV=get_partition_table_csv(variants_dir))

partition_table = env.Command(
    join("$BUILD_DIR", "partitions.bin"),
    "$PARTITIONS_TABLE_CSV",
    env.VerboseAction(
        '"$PYTHONEXE" "%s" -q $SOURCE $TARGET' % join(FRAMEWORK_DIR, "tools", "gen_esp32part.py"),
        "Generating partitions $TARGET",
    ),
)
env.Depends("$BUILD_DIR/$PROGNAME$PROGSUFFIX", partition_table)

#
#  Adjust the `esptoolpy` command in the `ElfToBin` builder with firmware checksum offset
#

action = deepcopy(env["BUILDERS"]["ElfToBin"].action)
action.cmd_list = env["BUILDERS"]["ElfToBin"].action.cmd_list.replace("-o", "--elf-sha256-offset 0xb0 -o")
env["BUILDERS"]["ElfToBin"].action = action
