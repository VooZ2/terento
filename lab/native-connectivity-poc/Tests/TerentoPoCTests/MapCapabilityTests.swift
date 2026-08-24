import Foundation

@main
struct MapCapabilityTests {
    static func main() {
        let registry = GarminMapCapabilityRegistry.local

        expect(
            registry.evaluate(identity: identity(model: "fēnix 7")) == .supported,
            "fēnix 7 is enabled by the Map Manager capability list"
        )
        expect(
            registry.evaluate(identity: identity(model: "Forerunner 970")) == .supported,
            "Forerunner 970 is enabled by the Map Manager capability list"
        )
        expect(
            registry.evaluate(identity: identity(model: "MARQ Adventurer (Gen 2)")) == .supported,
            "MARQ models are enabled by the Map Manager capability list"
        )
        expect(
            registry.evaluate(identity: identity(model: "Lily 2 Active"))
                == .unsupported(reason: "Garmin Map Manager does not list this model for additional maps."),
            "Lily 2 Active stays visible but map actions are disabled"
        )
        expect(
            registry.evaluate(identity: identity(model: "Approach S70"))
                == .unsupported(reason: "This model uses Garmin golf CourseView maps, not additional Terento maps."),
            "Approach S70 is excluded because its Map Manager maps are golf-only"
        )
        expect(
            registry.evaluate(identity: identity(model: "Garmin Future Watch")) == .unknown,
            "an unrecognised Garmin model fails closed with unknown map support"
        )
        print("PASS: 6 Map Manager capability tests")
    }

    private static func identity(model: String) -> DeviceIdentity {
        DeviceIdentity(
            manufacturer: "Garmin",
            model: model,
            family: nil,
            variant: nil,
            usbVendorId: 0x091e,
            usbProductId: 0xffff,
            firmware: nil,
            storageCapacity: 0,
            freeSpace: 0
        )
    }

    private static func expect(_ condition: Bool, _ message: String) {
        guard condition else { fatalError("FAIL: \(message)") }
        print("PASS: \(message)")
    }
}
