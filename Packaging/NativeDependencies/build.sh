#!/bin/sh

set -eu

LIBUSB_VERSION="1.0.30"
LIBUSB_ARCHIVE="libusb-${LIBUSB_VERSION}.tar.bz2"
LIBUSB_URL="https://github.com/libusb/libusb/releases/download/v${LIBUSB_VERSION}/${LIBUSB_ARCHIVE}"
LIBUSB_SHA256="fea36f34f9156400209595e300840767ab1a385ede1dc7ee893015aea9c6dbaf"

LIBMTP_VERSION="1.1.23"
LIBMTP_ARCHIVE="libmtp-${LIBMTP_VERSION}.tar.gz"
LIBMTP_URL="https://downloads.sourceforge.net/project/libmtp/libmtp/${LIBMTP_VERSION}/${LIBMTP_ARCHIVE}"
LIBMTP_SHA256="74a2b6e8cb4a0304e95b995496ea3ac644c29371649b892b856e22f12a0bdeed"

deployment_target="${MACOSX_DEPLOYMENT_TARGET:-13.0}"
architecture="${CURRENT_ARCH:-arm64}"
output_dir=""
bundle_contents=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        --output)
            output_dir="$2"
            shift 2
            ;;
        --deployment-target)
            deployment_target="$2"
            shift 2
            ;;
        --arch)
            architecture="$2"
            shift 2
            ;;
        --bundle)
            bundle_contents="$2"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

if [ -z "$output_dir" ]; then
    echo "Usage: $0 --output DIR [--deployment-target VERSION] [--arch ARCH] [--bundle APP_CONTENTS]" >&2
    exit 2
fi

case "$architecture" in
    arm64)
        ;;
    *)
        echo "Terento production native dependencies currently support arm64 only; got: $architecture" >&2
        exit 1
        ;;
esac

case "$deployment_target" in
    13.*|14.*|15.*|16.*|17.*|18.*|19.*|20.*|21.*|22.*|23.*|24.*|25.*|26.*)
        ;;
    *)
        echo "Unexpected macOS deployment target: $deployment_target" >&2
        exit 1
        ;;
esac

if [ "$(uname -s)" != "Darwin" ]; then
    echo "Terento native dependency build requires macOS" >&2
    exit 1
fi

src_dir="$output_dir/source"
download_dir="$output_dir/downloads"
prefix_dir="$output_dir/prefix"
libusb_prefix="$prefix_dir/libusb"
libmtp_prefix="$prefix_dir/libmtp"
bundle_lib_dir="$output_dir/lib"
bundle_include_dir="$output_dir/include"
build_marker="$output_dir/.terento-native-dependencies-${LIBUSB_VERSION}-${LIBMTP_VERSION}-${architecture}-macos-${deployment_target}"

mkdir -p "$src_dir" "$download_dir" "$prefix_dir" "$bundle_lib_dir" "$bundle_include_dir"

download_and_verify() {
    archive_path="$1"
    url="$2"
    expected_sha256="$3"

    if [ ! -f "$archive_path" ]; then
        curl --fail --location --silent --show-error "$url" --output "$archive_path"
    fi

    actual_sha256="$(shasum -a 256 "$archive_path" | awk '{print $1}')"
    if [ "$actual_sha256" != "$expected_sha256" ]; then
        echo "Checksum mismatch for $(basename "$archive_path")" >&2
        echo "Expected: $expected_sha256" >&2
        echo "Actual:   $actual_sha256" >&2
        exit 1
    fi
}

extract_once() {
    archive_path="$1"
    expected_directory="$2"
    extract_format="$3"

    if [ ! -d "$src_dir/$expected_directory" ]; then
        case "$extract_format" in
            bz2)
                tar -xjf "$archive_path" -C "$src_dir"
                ;;
            gz)
                tar -xzf "$archive_path" -C "$src_dir"
                ;;
            *)
                echo "Unknown archive format: $extract_format" >&2
                exit 2
                ;;
        esac
    fi
}

assert_arm64_and_minimum_target() {
    dylib_path="$1"
    expected_install_name="$2"

    if ! lipo -archs "$dylib_path" | tr ' ' '\n' | grep -qx "$architecture"; then
        echo "Unexpected architecture in $dylib_path" >&2
        exit 1
    fi

    install_name="$(otool -D "$dylib_path" | sed -n '2p')"
    if [ "$install_name" != "$expected_install_name" ]; then
        echo "Unexpected install name for $dylib_path: $install_name" >&2
        exit 1
    fi

    minimum_target="$(otool -l "$dylib_path" | awk '/LC_BUILD_VERSION/{seen=1; next} seen && /minos/{print $2; exit}')"
    if [ "$minimum_target" != "$deployment_target" ]; then
        echo "Unexpected minimum macOS target in $dylib_path: $minimum_target" >&2
        echo "Expected: $deployment_target" >&2
        exit 1
    fi

    if otool -L "$dylib_path" | grep -E '/opt/homebrew|/usr/local|/Users/' >/dev/null; then
        echo "Developer-machine dependency found in $dylib_path" >&2
        otool -L "$dylib_path" >&2
        exit 1
    fi
}

if [ ! -f "$build_marker" ]; then
    libusb_source="$src_dir/libusb-${LIBUSB_VERSION}"
    libmtp_source="$src_dir/libmtp-${LIBMTP_VERSION}"

    download_and_verify "$download_dir/$LIBUSB_ARCHIVE" "$LIBUSB_URL" "$LIBUSB_SHA256"
    download_and_verify "$download_dir/$LIBMTP_ARCHIVE" "$LIBMTP_URL" "$LIBMTP_SHA256"
    extract_once "$download_dir/$LIBUSB_ARCHIVE" "libusb-${LIBUSB_VERSION}" bz2
    extract_once "$download_dir/$LIBMTP_ARCHIVE" "libmtp-${LIBMTP_VERSION}" gz

    common_cflags="-arch $architecture -mmacosx-version-min=$deployment_target"

    if [ ! -f "$libusb_prefix/lib/libusb-1.0.0.dylib" ]; then
        (
            cd "$libusb_source"
            lt_cv_sys_max_cmd_len=1048576 \
            CFLAGS="$common_cflags" \
            LDFLAGS="$common_cflags -Wl,-install_name,@rpath/libusb-1.0.0.dylib" \
            ./configure \
                --prefix="$libusb_prefix" \
                --disable-static \
                --enable-shared \
                --disable-udev \
                --disable-examples-build \
                --disable-tests-build
            make
            make install
        )
    fi

    if [ ! -f "$libmtp_prefix/lib/libmtp.9.dylib" ]; then
        pkg_config_path="$(command -v pkg-config 2>/dev/null || true)"
        if [ -z "$pkg_config_path" ]; then
            pkg_config_path="/usr/bin/true"
        fi

        (
            cd "$libmtp_source"
            lt_cv_sys_max_cmd_len=1048576 \
            PKG_CONFIG="$pkg_config_path" \
            CFLAGS="$common_cflags" \
            CPPFLAGS="-I$libusb_prefix/include/libusb-1.0" \
            LDFLAGS="$common_cflags -L$libusb_prefix/lib -Wl,-install_name,@rpath/libmtp.9.dylib" \
            LIBUSB_CFLAGS="-I$libusb_prefix/include/libusb-1.0" \
            LIBUSB_LIBS="-L$libusb_prefix/lib -lusb-1.0" \
            PKG_CONFIG_PATH="$libusb_prefix/lib/pkgconfig" \
            ./configure \
                --prefix="$libmtp_prefix" \
                --disable-static \
                --enable-shared \
                --disable-rpath \
                --disable-doxygen
            make
            make install
        )
    fi

    cp "$libusb_prefix/lib/libusb-1.0.0.dylib" "$bundle_lib_dir/libusb-1.0.0.dylib"
    cp "$libmtp_prefix/lib/libmtp.9.dylib" "$bundle_lib_dir/libmtp.9.dylib"
    cp "$libusb_prefix/include/libusb-1.0/libusb.h" "$bundle_include_dir/libusb.h"
    cp "$libmtp_prefix/include/libmtp.h" "$bundle_include_dir/libmtp.h"
    : > "$build_marker"
fi

# The compiler resolves `-lmtp` through the unversioned development name. The
# app bundle itself receives only the versioned dylib below. Keep the matching
# libusb development name in the build directory as well: Xcode links with
# `-lusb-1.0`, while the shipped binary remains the versioned dylib.
ln -sf "libmtp.9.dylib" "$bundle_lib_dir/libmtp.dylib"
ln -sf "libusb-1.0.0.dylib" "$bundle_lib_dir/libusb-1.0.dylib"

assert_arm64_and_minimum_target "$bundle_lib_dir/libusb-1.0.0.dylib" "@rpath/libusb-1.0.0.dylib"
assert_arm64_and_minimum_target "$bundle_lib_dir/libmtp.9.dylib" "@rpath/libmtp.9.dylib"

if [ -n "$bundle_contents" ]; then
    bundle_frameworks="$bundle_contents/Frameworks"
    mkdir -p "$bundle_frameworks"
    cp "$bundle_lib_dir/libmtp.9.dylib" "$bundle_frameworks/libmtp.9.dylib"
    cp "$bundle_lib_dir/libusb-1.0.0.dylib" "$bundle_frameworks/libusb-1.0.0.dylib"
fi
