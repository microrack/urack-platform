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
Arduino Framework with Pre-compiled Libraries

Delegates to pioarduino-build.py (adapted) which configures all paths.
"""

import os
from os.path import join, isfile
from SCons.Script import DefaultEnvironment, SConscript

env = DefaultEnvironment()
platform = env.PioPlatform()

FRAMEWORK_DIR = platform.get_dir()
PREBUILT_DIR = join(FRAMEWORK_DIR, "prebuilt")
PREBUILT_LIB = join(PREBUILT_DIR, "liburack_arduino.a")

# Call adapted pioarduino-build.py which sets up all Arduino paths
print("URack Arduino: Loading pioarduino-build.py...")
SConscript(join(platform.get_dir(), "builder", "frameworks", "pioarduino-build.py"))
print("URack Arduino: pioarduino-build.py loaded")

# Add pre-compiled library to link
if isfile(PREBUILT_LIB):
    env.Prepend(LIBS=["urack_arduino"])
    env.Append(LIBPATH=[PREBUILT_DIR])
    print("Using pre-compiled Arduino library: %s" % PREBUILT_LIB)
else:
    print("Warning: Pre-compiled library not found at: %s" % PREBUILT_LIB)
    print("Please run: cd urack-platform && python3 build_precompiled_libs.py")
