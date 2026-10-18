#!/bin/bash
# Build old-OS compatible OCR dependencies from public source, not modern Homebrew bottles.
set -euo pipefail
cd "$(dirname "$0")/.."
base="$PWD/.legacy-native"
mkdir -p "$base/src" "$base/prefix" vendor/tesseract vendor/antiword
prefix="$base/prefix"
export MACOSX_DEPLOYMENT_TARGET=10.13
export CFLAGS='-O2 -mmacosx-version-min=10.13 -march=x86-64'
export CXXFLAGS="$CFLAGS"
export CPPFLAGS="-I$prefix/include"
export LDFLAGS="-L$prefix/lib -mmacosx-version-min=10.13"
export PKG_CONFIG_LIBDIR="$prefix/lib/pkgconfig"
fetch() { curl --fail --location --retry 3 "$1" -o "$base/src/$2"; }
fetch https://download.sourceforge.net/libpng/libpng-1.6.43.tar.xz libpng.tar.xz
fetch https://github.com/DanBloomberg/leptonica/releases/download/1.82.0/leptonica-1.82.0.tar.gz leptonica.tar.gz
fetch https://github.com/tesseract-ocr/tesseract/archive/refs/tags/4.1.3.tar.gz tesseract.tar.gz
fetch https://cran.r-project.org/src/contrib/antiword_1.3.5.tar.gz antiword.tar.gz
cd "$base/src"
tar xf libpng.tar.xz
tar xf leptonica.tar.gz
tar xf tesseract.tar.gz
tar xf antiword.tar.gz
(cd libpng-1.6.43 && ./configure --prefix="$prefix" --disable-shared --enable-static && make -j4 && make install)
(cd leptonica-1.82.0 && ./configure --prefix="$prefix" --disable-shared --enable-static --without-libjpeg --without-libtiff --without-giflib --without-libwebp --without-libopenjpeg && make -j4 && make install)
(cd tesseract-4.1.3 && ./autogen.sh && ./configure --prefix="$prefix" --disable-shared --enable-static --disable-openmp --disable-graphics --without-curl --without-archive && make -j4 && make install)
(cd antiword/src && make -f Makevars CC=clang "CFLAGS=$CFLAGS -DNDEBUG")
cd ../..
cp "$prefix/bin/tesseract" vendor/tesseract/tesseract
cp "$base/src/antiword/src/antiword" vendor/antiword/antiword
cp -R "$base/src/antiword/src/share/antiword/." vendor/antiword/
mkdir -p vendor/licenses/legacy-native-source
cp "$base/src/"*.tar.* vendor/licenses/legacy-native-source/
shasum -a 256 "$base/src/"*.tar.* > vendor/licenses/legacy-native-source/SHA256.txt
