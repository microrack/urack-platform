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

import re
import sys
from os.path import isfile, join

from SCons.Script import (ARGUMENTS, COMMAND_LINE_TARGETS, AlwaysBuild,
                          Builder, Default, DefaultEnvironment)

from platformio.util import get_serial_ports

env = DefaultEnvironment()
platform = env.PioPlatform()
board = env.BoardConfig()
mcu = board.get("build.mcu", "esp32")

#
# Helpers
#

def BeforeUpload(target, source, env):
    upload_options = {}
    if "BOARD" in env:
        upload_options = env.BoardConfig().get("upload", {})

    env.AutodetectUploadPort()

    before_ports = get_serial_ports()
    if upload_options.get("use_1200bps_touch", False):
        env.TouchSerialPort("$UPLOAD_PORT", 1200)

    if upload_options.get("wait_for_upload_port", False):
        env.Replace(UPLOAD_PORT=env.WaitForNewSerialPort(before_ports))


def PrintUploadInfo(target, source, env):
    """Print information about files to be uploaded"""
    import sys
    sys.stdout.flush()
    
    print("\n" + "=" * 60)
    print("URack Upload Configuration")
    print("=" * 60)
    
    flash_images = env.get("FLASH_EXTRA_IMAGES", [])
    if not flash_images:
        print("  WARNING: No FLASH_EXTRA_IMAGES found!")
    
    # Print extra images (bootloader, partitions, boot_app0)
    for image in flash_images:
        offset = image[0]
        filepath = env.subst(image[1])
        filename = filepath.split("/")[-1] if "/" in filepath else filepath.split("\\")[-1]
        print(f"  {offset:8s} -> {filename:25s} ({filepath})")
    
    # Print firmware
    app_offset = env.subst("$ESP32_APP_OFFSET")
    if not app_offset or app_offset == "$ESP32_APP_OFFSET":
        app_offset = "0x10000"
    source_path = str(source[0]) if source else "firmware.bin"
    source_name = source_path.split("/")[-1] if "/" in source_path else source_path.split("\\")[-1]
    print(f"  {app_offset:8s} -> {source_name:25s} ({source_path})")
    
    print("=" * 60 + "\n")
    sys.stdout.flush()


def _to_unix_slashes(path):
    return path.replace("\\", "/")

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

#
# Target: Upload firmware
#

PREBUILT_DIR = join(platform.get_dir(), "prebuilt")

upload_protocol = env.subst("$UPLOAD_PROTOCOL")
debug_tools = board.get("debug.tools", {})
upload_actions = []

# Compatibility with old OTA configurations
if (upload_protocol != "espota"
        and re.match(r"\"?((([0-9]{1,3}\.){3}[0-9]{1,3})|[^\\/]+\.local)\"?$",
                     env.get("UPLOAD_PORT", ""))):
    upload_protocol = "espota"
    sys.stderr.write(
        "Warning! We have just detected `upload_port` as IP address or host "
        "name of ESP device. `upload_protocol` is switched to `espota`.\n"
        "Please specify `upload_protocol = espota` in `platformio.ini` "
        "project configuration file.\n")

if upload_protocol == "espota":
    if not env.subst("$UPLOAD_PORT"):
        sys.stderr.write(
            "Error: Please specify IP address or host name of ESP device "
            "using `upload_port` for build environment or use "
            "global `--upload-port` option.\n"
            "See https://docs.platformio.org/page/platforms/"
            "espressif32.html#over-the-air-ota-update\n")
    
    # Find espota.py in Arduino framework or use from prebuilt
    espota_script = join(PREBUILT_DIR, "include", "arduino", "tools", "espota.py")
    if not isfile(espota_script):
        sys.stderr.write("Error: espota.py not found in prebuilt\n")
        env.Exit(1)
    
    env.Replace(
        UPLOADER=espota_script,
        UPLOADERFLAGS=["--debug", "--progress", "-i", "$UPLOAD_PORT"],
        UPLOADCMD='"$PYTHONEXE" "$UPLOADER" $UPLOADERFLAGS -f $SOURCE'
    )
    if set(["uploadfs", "uploadfsota"]) & set(COMMAND_LINE_TARGETS):
        env.Append(UPLOADERFLAGS=["--spiffs"])
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]

elif upload_protocol == "esptool":
    env.Replace(
        UPLOADER=join(
            platform.get_package_dir("tool-esptoolpy") or "", "esptool.py"),
        UPLOADERFLAGS=[
            "--chip", mcu,
            "--port", '"$UPLOAD_PORT"',
            "--baud", "$UPLOAD_SPEED",
            "--before", board.get("upload.before_reset", "default_reset"),
            "--after", board.get("upload.after_reset", "hard_reset"),
            "write_flash", "-z",
            "--flash_mode", "${__get_board_flash_mode(__env__)}",
            "--flash_freq", "${__get_board_f_image(__env__)}",
            "--flash_size", "detect"
        ],
        UPLOADCMD='"$PYTHONEXE" "$UPLOADER" $UPLOADERFLAGS $ESP32_APP_OFFSET $SOURCE'
    )
    
    # Add extra images from prebuilt (bootloader, partitions, boot_app0)
    for image in env.get("FLASH_EXTRA_IMAGES", []):
        env.Append(UPLOADERFLAGS=[image[0], env.subst(image[1])])

    if "uploadfs" in COMMAND_LINE_TARGETS:
        env.Replace(
            UPLOADERFLAGS=[
                "--chip", mcu,
                "--port", '"$UPLOAD_PORT"',
                "--baud", "$UPLOAD_SPEED",
                "--before", board.get("upload.before_reset", "default_reset"),
                "--after", board.get("upload.after_reset", "hard_reset"),
                "write_flash", "-z",
                "--flash_mode", "${__get_board_flash_mode(__env__)}",
                "--flash_freq", "${__get_board_f_image(__env__)}",
                "--flash_size", "detect",
                "$FS_START"
            ],
            UPLOADCMD='"$PYTHONEXE" "$UPLOADER" $UPLOADERFLAGS $SOURCE',
        )
        upload_actions = [
            env.VerboseAction(BeforeUpload, "Looking for upload port..."),
            env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")
        ]
    else:
        upload_actions = [
            env.VerboseAction(PrintUploadInfo, "Preparing upload..."),
            env.VerboseAction(BeforeUpload, "Looking for upload port..."),
            env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")
        ]

elif upload_protocol == "dfu":
    hwids = board.get("build.hwids", [["0x2341", "0x0070"]])
    
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]
    
    env.Replace(
        UPLOADER=join(
            platform.get_package_dir("tool-dfuutil-arduino") or "", "dfu-util"
        ),
        UPLOADERFLAGS=[
            "-d",
            ",".join(["%s:%s" % (hwid[0], hwid[1]) for hwid in hwids]),
            "-Q",
            "-D"
        ],
        UPLOADCMD='"$UPLOADER" $UPLOADERFLAGS "$SOURCE"',
    )

elif upload_protocol in debug_tools:
    openocd_args = ["-d%d" % (2 if int(ARGUMENTS.get("PIOVERBOSE", 0)) else 1)]
    openocd_args.extend(
        debug_tools.get(upload_protocol).get("server").get("arguments", []))
    openocd_args.extend(
        [
            "-c",
            "adapter speed %s" % env.GetProjectOption("debug_speed", "5000"),
            "-c",
            "program_esp {{$SOURCE}} %s verify"
            % (
                "$FS_START"
                if "uploadfs" in COMMAND_LINE_TARGETS
                else env.get("ESP32_APP_OFFSET", "0x10000")
            ),
        ]
    )
    if "uploadfs" not in COMMAND_LINE_TARGETS:
        for image in env.get("FLASH_EXTRA_IMAGES", []):
            openocd_args.extend(
                [
                    "-c",
                    "program_esp {{%s}} %s verify"
                    % (_to_unix_slashes(image[1]), image[0]),
                ]
            )
    openocd_args.extend(["-c", "reset run; shutdown"])
    openocd_args = [
        f.replace(
            "$PACKAGE_DIR",
            _to_unix_slashes(
                platform.get_package_dir("tool-openocd-esp32") or ""))
        for f in openocd_args
    ]
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

env.AddPlatformTarget("upload", target_firm, upload_actions, "Upload")
env.AddPlatformTarget("uploadfs", target_firm, upload_actions, "Upload Filesystem Image")

#
# Target: Erase Flash and Upload
#

env.AddPlatformTarget(
    "erase_upload",
    target_firm,
    [
        env.VerboseAction(BeforeUpload, "Looking for upload port..."),
        env.VerboseAction(
            '"$PYTHONEXE" "$OBJCOPY" --chip %s --port "$UPLOAD_PORT" erase_flash' % mcu,
            "Erasing..."
        ),
        env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")
    ],
    "Erase Flash and Upload",
)

#
# Target: Erase Flash
#

env.AddPlatformTarget(
    "erase",
    None,
    [
        env.VerboseAction(BeforeUpload, "Looking for upload port..."),
        env.VerboseAction(
            '"$PYTHONEXE" "$OBJCOPY" --chip %s --port "$UPLOAD_PORT" erase_flash' % mcu,
            "Erasing..."
        )
    ],
    "Erase Flash",
)

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

