import Foundation

/// Presentation data for the existing Device screen. Compatibility is the
/// canonical API result; the catalog contributes only optional artwork metadata.
struct DevicePresentation: Equatable, Sendable {
    let identity: DeviceIdentity
    let deviceName: String
    let variant: String
    let compatibility: CompatibilityStatus?
    let mapSupport: GarminMapSupportStatus
    let asset: ResolvedDeviceAsset
    let assetURL: URL?
    let cachedAssetURL: URL?
    let assetAttribution: String?
    let assetSource: DeviceAssetSource?
    let attributionRequired: Bool
    let legalManufacturerNotice: Bool?
    let legalNotice: String?

    init(
        identity: DeviceIdentity,
        deviceName: String,
        variant: String,
        compatibility: CompatibilityStatus?,
        asset: ResolvedDeviceAsset
    ) {
        self.identity = identity
        self.deviceName = deviceName
        self.variant = variant
        self.compatibility = compatibility
        self.mapSupport = GarminMapCapabilityRegistry.local.evaluate(identity: identity)
        self.asset = asset
        self.assetURL = asset.assetURL
        self.cachedAssetURL = asset.cachedFileURL
        self.assetAttribution = asset.attribution
        self.assetSource = asset.assetSource
        self.attributionRequired = asset.attributionRequired
        self.legalManufacturerNotice = asset.legalManufacturerNotice
        self.legalNotice = asset.legalNotice
    }
}
