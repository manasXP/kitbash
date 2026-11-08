// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "EpicuraKit",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "EpicuraKit", targets: ["EpicuraKit"])],
    targets: [
        .target(name: "EpicuraKit"),
        .testTarget(name: "EpicuraKitTests", dependencies: ["EpicuraKit"]),
    ]
)
