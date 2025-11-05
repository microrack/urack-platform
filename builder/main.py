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

import sys
from os.path import join

from SCons.Script import (ARGUMENTS, COMMAND_LINE_TARGETS, AlwaysBuild,
                          Builder, Default, DefaultEnvironment)

from platformio.util import get_serial_ports

env = DefaultEnvironment()
platform = env.PioPlatform()

env.Replace(
    AR="xtensa-esp32-elf-ar",
    AS="xtensa-esp32-elf-as",
    CC="xtensa-esp32-elf-gcc",
    CXX="xtensa-esp32-elf-g++",
    GDB="xtensa-esp32-elf-gdb",
    OBJCOPY=join(platform.get_package_dir("tool-esptoolpy") or "", "esptool.py"),
    RANLIB="xtensa-esp32-elf-ranlib",
    SIZETOOL="xtensa-esp32-elf-size",

    ARFLAGS=["rc"],

    SIZEPROGREGEXP=r"^(?:\.iram0\.text|\.iram0\.vectors|\.dram0\.data|\.flash\.text|\.flash\.rodata|)\s+(\d+).*",
    SIZEDATAREGEXP=r"^(?:\.dram0\.data|\.dram0\.bss|\.noinit)\s+(\d+).*",
    SIZECHECKCMD="$SIZETOOL -A -d $SOURCES",
    SIZEPRINTCMD='$SIZETOOL -B -d $SOURCES',

    PROGSUFFIX=".elf"
)

# Allow user to override via pre:script
if env.get("PROGNAME", "program") == "program":
    env.Replace(PROGNAME="firmware")

env.Append(
    BUILDERS=dict(
        ElfToBin=Builder(
            action=env.VerboseAction(" ".join([
                '"$PYTHONEXE" "$OBJCOPY"',
                "--chip", "esp32",
                "elf2image",
                "--flash_mode", "${__get_board_flash_mode(__env__)}",
                "--flash_freq", "${__get_board_f_image(__env__)}",
                "--flash_size", env.BoardConfig().get("upload.flash_size", "4MB"),
                "-o", "$TARGET",
                "$SOURCES"
            ]), "Building $TARGET"),
            suffix=".bin"
        )
    )
)

# Target: Build executable and linkable firmware
target_elf = None
if "nobuild" in COMMAND_LINE_TARGETS:
    target_elf = join("$BUILD_DIR", "${PROGNAME}.elf")
    target_firm = join("$BUILD_DIR", "${PROGNAME}.bin")
else:
    target_elf = env.BuildProgram()
    target_firm = env.ElfToBin(join("$BUILD_DIR", "${PROGNAME}"), target_elf)
    env.Depends(target_firm, "checkprogsize")

AlwaysBuild(env.Alias("nobuild", target_firm))
target_buildprog = env.Alias("buildprog", target_firm, target_firm)

# Target: Print binary size
target_size = env.Alias(
    "size", target_elf,
    env.VerboseAction("$SIZEPRINTCMD", "Calculating size $SOURCE"))
AlwaysBuild(target_size)

# Target: Upload by default .bin file
upload_protocol = env.subst("$UPLOAD_PROTOCOL")
debug_tools = env.BoardConfig().get("debug.tools", {})
upload_source = target_firm
upload_actions = []

if upload_protocol.startswith("esptool"):
    env.Replace(
        UPLOADER=join(platform.get_package_dir("tool-esptoolpy") or "", "esptool.py"),
        UPLOADERFLAGS=[
            "--chip", "esp32",
            "--port", '"$UPLOAD_PORT"',
            "--baud", "$UPLOAD_SPEED",
            "--before", "default_reset",
            "--after", "hard_reset",
            "write_flash", "-z",
            "--flash_mode", "${__get_board_flash_mode(__env__)}",
            "--flash_freq", "${__get_board_f_flash(__env__)}",
            "--flash_size", "detect"
        ],
        UPLOADCMD='"$PYTHONEXE" "$UPLOADER" $UPLOADERFLAGS 0x1000 "$SOURCE"'
    )
    upload_actions = [
        env.VerboseAction(env.AutodetectUploadPort, "Looking for upload port..."),
        env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")
    ]

elif upload_protocol in debug_tools:
    openocd_args = [
        "-d%d" % (2 if int(ARGUMENTS.get("PIOVERBOSE", 0)) else 1)
    ]
    openocd_args.extend(
        debug_tools.get(upload_protocol).get("server").get("arguments", []))
    openocd_args.extend([
        "-c", "program_esp {{$SOURCE}} %s verify" %
        env.BoardConfig().get("upload.offset_address", "0x10000"),
        "-c", "reset run; shutdown"
    ])
    env.Replace(
        UPLOADER="openocd",
        UPLOADERFLAGS=openocd_args,
        UPLOADCMD="$UPLOADER $UPLOADERFLAGS",
    )
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]

# custom upload tool
elif upload_protocol == "custom":
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]

else:
    sys.stderr.write("Warning! Unknown upload protocol %s\n" % upload_protocol)

AlwaysBuild(env.Alias("upload", upload_source, upload_actions))

# Target: Define targets
Default([target_buildprog, target_size])


def __get_board_flash_mode(env):
    mode = env.subst("$BOARD_FLASH_MODE")
    if mode in ("qio", "qout"):
        return "dio"
    return mode


def __get_board_f_flash(env):
    frequency = env.subst("$BOARD_F_FLASH")
    frequency = str(frequency).replace("L", "")
    return str(int(int(frequency) / 1000000)) + "m"


def __get_board_f_image(env):
    board_config = env.BoardConfig()
    if "build.f_image" in board_config:
        frequency = board_config.get("build.f_image")
        frequency = str(frequency).replace("L", "")
        return str(int(int(frequency) / 1000000)) + "m"
    return __get_board_f_flash(env)


def __get_board_f_boot(env):
    board_config = env.BoardConfig()
    if "build.f_boot" in board_config:
        frequency = board_config.get("build.f_boot")
        frequency = str(frequency).replace("L", "")
        return str(int(int(frequency) / 1000000)) + "m"
    return __get_board_f_flash(env)


def __get_board_boot_mode(env):
    board_config = env.BoardConfig()
    memory_type = board_config.get("build.arduino.memory_type", "")
    build_boot = board_config.get("build.boot", "$BOARD_FLASH_MODE")
    if memory_type in ("opi_opi", "opi_qspi"):
        build_boot = "opi"
    if build_boot == "$BOARD_FLASH_MODE":
        return env.subst("$BOARD_FLASH_MODE")
    return build_boot


env.Replace(
    __get_board_flash_mode=__get_board_flash_mode,
    __get_board_f_flash=__get_board_f_flash,
    __get_board_f_image=__get_board_f_image,
    __get_board_f_boot=__get_board_f_boot,
    __get_board_boot_mode=__get_board_boot_mode
)

