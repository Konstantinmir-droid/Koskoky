#!/bin/bash
# Qt5's JPEG plugin needs the JPEG8 ABI; modern Homebrew binaries require macOS 14.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .legacy-jpeg vendor/compat vendor/licenses/legacy-jpeg-source
curl --fail --location --retry 3 https://github.com/libjpeg-turbo/libjpeg-turbo/archive/refs/tags/2.1.5.1.tar.gz -o .legacy-jpeg/source.tar.gz
tar xf .legacy-jpeg/source.tar.gz -C .legacy-jpeg
cmake -S .legacy-jpeg/libjpeg-turbo-2.1.5.1 -B .legacy-jpeg/build \
  -DCMAKE_OSX_DEPLOYMENT_TARGET=10.13 -DCMAKE_OSX_ARCHITECTURES=x86_64 \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DCMAKE_C_FLAGS='-march=x86-64' \
  -DWITH_JPEG8=ON -DWITH_SIMD=OFF -DENABLE_SHARED=ON -DENABLE_STATIC=OFF
cmake --build .legacy-jpeg/build --parallel 4
cp -L .legacy-jpeg/build/libjpeg.8.dylib vendor/compat/libjpeg.8.dylib
cp .legacy-jpeg/source.tar.gz vendor/licenses/legacy-jpeg-source/
cp .legacy-jpeg/libjpeg-turbo-2.1.5.1/LICENSE.md vendor/licenses/legacy-jpeg-source/
shasum -a 256 .legacy-jpeg/source.tar.gz > vendor/licenses/legacy-jpeg-source/SHA256.txt
