import XCTest
@testable import EpicuraKit

final class CookingProgressTests: XCTestCase {
    func testFractionIsClamped() {
        XCTAssertEqual(CookingProgress.fraction(elapsed: 30, total: 60), 0.5)
        XCTAssertEqual(CookingProgress.fraction(elapsed: 90, total: 60), 1)
        XCTAssertEqual(CookingProgress.fraction(elapsed: -5, total: 60), 0)
        XCTAssertEqual(CookingProgress.fraction(elapsed: 0, total: 0), 1)
    }

    func testRemainingNeverNegative() {
        XCTAssertEqual(CookingProgress.remainingSeconds(elapsed: 59.2, total: 60), 1)
        XCTAssertEqual(CookingProgress.remainingSeconds(elapsed: 75, total: 60), 0)
    }
}
