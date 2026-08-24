// swift-tools-version: 6.0

import Foundation
import PackageDescription

let libMTPPrefix = ProcessInfo.processInfo.environment["LIBMTP_PREFIX"]
    ?? "/opt/homebrew/opt/libmtp"
let libUSBPrefix = ProcessInfo.processInfo.environment["LIBUSB_PREFIX"]
    ?? "/opt/homebrew/opt/libusb"

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
                .unsafeFlags([
                    "-I\(libMTPPrefix)/include",
                    "-I\(libUSBPrefix)/include/libusb-1.0"
                ])
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
                    "-lmtp",
                    "-L\(libUSBPrefix)/lib",
                    "-lusb-1.0"
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
                    "-lmtp",
                    "-L\(libUSBPrefix)/lib",
                    "-lusb-1.0"
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
                    "-lmtp",
                    "-L\(libUSBPrefix)/lib",
                    "-lusb-1.0"
                ])
            ]
        )
    ]
)
