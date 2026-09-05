import Foundation
#if canImport(LibMTPBridge)
import LibMTPBridge
#endif

/// Keeps every UTF-8 buffer alive for exactly the synchronous native call.
/// The C bridge must never retain this profile or any string pointer.
func withNativeMapOperationProfile<Result>(
    _ profile: DeviceMapOperationProfile,
    _ body: (UnsafePointer<TerentoMTPMapOperationProfile>) throws -> Result
) rethrows -> Result {
    try profile.manufacturer.withCString { manufacturer in
        try profile.rawModel.withCString { model in
            try profile.targetDirectory.withCString { targetDirectory in
                var native = TerentoMTPMapOperationProfile()
                native.version = profile.version
                native.vendor_id = profile.vendorID
                native.product_id = profile.productID
                native.manufacturer = manufacturer
                native.model = model
                native.target_directory = targetDirectory
                return try withUnsafePointer(to: &native, body)
            }
        }
    }
}
