import XCTest
import AppKit
@testable import Jetlag

/// The Files table decides whether to follow a newly appended row from where the user
/// left the scroller. That decision is the log panel's: a view resting within the last
/// few points of its content is "at the bottom" and keeps following, so a table stopped
/// a pixel short of the end is not treated as deliberately scrolled away.
final class TableTailFollowingTests: XCTestCase {

    func testAViewScrolledPastTheEndOfItsContentIsAtTheBottom() {
        XCTAssertTrue(TableTailFollowing.isAtBottom(visibleMaxY: 1000, documentHeight: 1000))
        XCTAssertTrue(TableTailFollowing.isAtBottom(visibleMaxY: 1200, documentHeight: 1000))
    }

    /// A short document that does not fill its clip view is at the bottom: there is
    /// nowhere else to be, and the first appended row must still be followed.
    func testAViewShorterThanItsClipIsAtTheBottom() {
        XCTAssertTrue(TableTailFollowing.isAtBottom(visibleMaxY: 400, documentHeight: 0))
    }

    func testTheLastPointsOfTheTailStillCountAsTheBottom() {
        let threshold = TableTailFollowing.bottomThreshold
        XCTAssertTrue(TableTailFollowing.isAtBottom(visibleMaxY: 1000 - threshold, documentHeight: 1000))
        XCTAssertFalse(TableTailFollowing.isAtBottom(visibleMaxY: 1000 - threshold - 1, documentHeight: 1000))
    }

    func testAViewScrolledWellClearOfTheTailIsNotAtTheBottom() {
        XCTAssertFalse(TableTailFollowing.isAtBottom(visibleMaxY: 500, documentHeight: 1000))
        XCTAssertFalse(TableTailFollowing.isAtBottom(visibleMaxY: 0, documentHeight: 1000))
    }
}
