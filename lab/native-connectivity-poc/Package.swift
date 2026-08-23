// swift-tools-version: 6.0

import Foundation
import PackageDescription

let libMTPPrefix = ProcessInfo.processInfo.environment["LIBMTP_PREFIX"]
    ?? "/opt/homebrew/opt/libmtp"

let package = Package(
    name: "TerentoPoC",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .executable(
            name: "TerentoPoC",
            targets: ["TerentoPoC"]
        ),
        .executable(
            name: "TerentoWriteTest",
            targets: ["TerentoWriteTest"]
        ),
        .executable(
            name: "TerentoInterruptionTest",
            targets: ["TerentoInterruptionTest"]
        )
    ],
    targets: [
        .target(
            name: "LibMTPBridge",
            path: "Sources/LibMTPBridge",
            publicHeadersPath: "include",
            cSettings: [
                .unsafeFlags(["-I\(libMTPPrefix)/include"])
            ]
        ),
        .executableTarget(
            name: "TerentoPoC",
            dependencies: ["LibMTPBridge"],
            path: "Sources/TerentoPoC",
            resources: [
                .process("Resources")
            ],
            linkerSettings: [
                .unsafeFlags([
                    "-L\(libMTPPrefix)/lib",
                    "-lmtp"
                ])
            ]
        ),
        .executableTarget(
            name: "TerentoWriteTest",
            dependencies: ["LibMTPBridge"],
            path: "Sources/TerentoWriteTest",
            linkerSettings: [
                .unsafeFlags([
                    "-L\(libMTPPrefix)/lib",
                    "-lmtp"
                ])
            ]
        ),
        .executableTarget(
            name: "TerentoInterruptionTest",
            dependencies: ["LibMTPBridge"],
            path: "Sources/TerentoInterruptionTest",
            linkerSettings: [
                .unsafeFlags([
                    "-L\(libMTPPrefix)/lib",
                    "-lmtp"
                ])
            ]
        )
    ]
)
