#!/bin/sh
# Cross-compile the SM-C200 injection tooling. Requires zig (brew install zig).
# Outputs into build/, which is copied to an SD card.
set -e
cd "$(dirname "$0")"
mkdir -p build
# ptrace injector (static, no libc dep) -- used by the probe/getpid diagnostics
zig cc -target arm-linux-musleabihf -mcpu=generic+v7a -static -O2 -s \
    -o build/rvf-inject rvf-inject.c
# LD_PRELOAD trigger .so (dynamic, glibc 2.13 to match the device)
zig cc -target arm-linux-gnueabihf.2.13 -shared -fPIC -O2 -s \
    -o build/rvftrig.so rvftrig.c -ldl -lpthread
echo "built:"; file build/rvf-inject build/rvftrig.so
