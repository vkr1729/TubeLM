// swift-tools-version: 6.0
import PackageDescription

var targets: [Target] = [
    .target(
        name: "TubeLMCore",
        dependencies: [],
        path: "Sources/TubeLMCore",
        resources: [
            .copy("Resources/data.json")
        ]
    ),
    .testTarget(
        name: "TubeLMCoreTests",
        dependencies: ["TubeLMCore"],
        path: "Tests/TubeLMCoreTests",
        resources: [
            .copy("Resources/mock_data.json")
        ]
    ),
]

var products: [Product] = [
    .library(name: "TubeLMCore", targets: ["TubeLMCore"]),
]

#if canImport(Darwin) || os(macOS) || os(iOS)
targets.append(
    .executableTarget(
        name: "TubeLMApp",
        dependencies: ["TubeLMCore"],
        path: "Sources/TubeLMApp"
    )
)
products.append(
    .executable(name: "TubeLMApp", targets: ["TubeLMApp"])
)
#endif

let package = Package(
    name: "TubeLM",
    platforms: [
        .iOS(.v17),
        .macOS(.v14)
    ],
    products: products,
    targets: targets
)
