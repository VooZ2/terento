# Terento native dependencies

The production macOS target builds and bundles these libraries from pinned
upstream source archives:

| Library | Version | License | Source |
| --- | --- | --- | --- |
| libmtp | 1.1.23 | LGPL-2.1-or-later | <https://github.com/libmtp/libmtp> |
| libusb | 1.0.30 | LGPL-2.1-or-later | <https://github.com/libusb/libusb> |

The archive URLs and SHA-256 values are pinned in `build.sh`. The build uses
Apple Silicon (`arm64`) and the Xcode target's `MACOSX_DEPLOYMENT_TARGET`.
The resulting shared libraries use these install names:

```text
@rpath/libmtp.9.dylib
@rpath/libusb-1.0.0.dylib
```

The Xcode target invokes the script before compiling the C bridge. It places
the build outputs in derived data, links against those outputs, and copies
only the two shared libraries into `Terento.app/Contents/Frameworks`.
Apple system frameworks and `/usr/lib/libiconv.2.dylib` remain system
dependencies and are not bundled.

To build the native dependencies independently:

```sh
Packaging/NativeDependencies/build.sh \
  --output /private/tmp/terento-native-dependencies \
  --deployment-target 13.0 \
  --arch arm64
```

The script does not use Homebrew libraries and fails if a produced dylib
contains `/opt/homebrew`, `/usr/local`, or a developer `/Users/...` path.
