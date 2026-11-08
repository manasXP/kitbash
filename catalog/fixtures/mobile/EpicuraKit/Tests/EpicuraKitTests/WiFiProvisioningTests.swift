import XCTest
@testable import EpicuraKit

final class WiFiProvisioningTests: XCTestCase {
    func testAsciiFrameLayout() throws {
        let frame = try WiFiProvisioning.frame(ssid: "Home", password: "secret")
        XCTAssertEqual(Array(frame), [0x01, 4] + Array("Home".utf8) + [6] + Array("secret".utf8))
    }

    func testTooLongSsidIsRejected() {
        let long = String(repeating: "a", count: 64)
        XCTAssertThrowsError(try WiFiProvisioning.frame(ssid: long, password: "x")) { error in
            XCTAssertEqual(error as? WiFiProvisioning.Error, .fieldTooLong("ssid"))
        }
    }
}
