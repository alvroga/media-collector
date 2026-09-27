// swift-tools-version: 5.9
import PackageDescription

// Native macOS front end for Media Collector (ADR-0006). It launches the Python engine
// (`python -m media_collector serve`) and talks JSON lines over stdio (docs/agent_docs/app-protocol.md).
// Dev build: `cd app && swift run MediaCollector`. Packaging into a signed .app comes later.
let package = Package(
    name: "MediaCollector",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(name: "MediaCollector", path: "Sources/MediaCollector"),
        .testTarget(name: "MediaCollectorTests", dependencies: ["MediaCollector"], path: "Tests/MediaCollectorTests"),
    ]
)
