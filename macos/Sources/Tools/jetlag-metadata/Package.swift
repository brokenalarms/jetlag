// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "jetlag-metadata",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(name: "jetlag-metadata", path: "Sources")
    ]
)
