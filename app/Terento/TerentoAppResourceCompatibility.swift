#if !SWIFT_PACKAGE
import Foundation

/// SwiftPM exposes `Bundle.module`; the Xcode application target uses its
/// main bundle for the same source-owned resources.
extension Bundle {
    static var module: Bundle { .main }
}
#endif
