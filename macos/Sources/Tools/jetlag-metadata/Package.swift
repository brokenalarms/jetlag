// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "jetlag-metadata",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "jetlag-metadata",
            path: "Sources"
        )
    ]
)
