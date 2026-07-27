#!/bin/sh
# Cross-compile the ptrace injector for the SM-C200 (ARMv7, static, no libc dep).
# Requires zig (brew install zig). Output: build/rvf-inject, copied to an SD card.
set -e
cd "$(dirname "$0")"
mkdir -p build
zig cc -target arm-linux-musleabihf -mcpu=generic+v7a -static -O2 -s \
    -o build/rvf-inject rvf-inject.c
echo "built build/rvf-inject:"
file build/rvf-inject
