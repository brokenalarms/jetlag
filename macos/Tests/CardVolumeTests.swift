import XCTest
@testable import Jetlag

/// Looking for cards must never read the boot disk or a fixed drive: those hold
/// Photos, Desktop and other apps' data, and reading them prompts for access.
final class CardVolumeTests: XCTestCase {

    func testBootDiskIsNeverACard() {
        XCTAssertFalse(CardVolume(isRootFileSystem: true, isRemovable: true, isEjectable: true).mayBeCard)
    }

    func testFixedDriveIsNeverACard() {
        XCTAssertFalse(CardVolume(isRootFileSystem: false, isRemovable: false, isEjectable: false).mayBeCard)
    }

    func testRemovableOrEjectableMediaMayBeACard() {
        XCTAssertTrue(CardVolume(isRootFileSystem: false, isRemovable: true, isEjectable: false).mayBeCard)
        XCTAssertTrue(CardVolume(isRootFileSystem: false, isRemovable: false, isEjectable: true).mayBeCard)
    }

    func testCardLayoutIsDCIMOrPRIVATEAtTheRoot() {
        XCTAssertTrue(CardVolume.hasCardLayout(topLevelNames: ["DCIM", "MISC"]))
        XCTAssertTrue(CardVolume.hasCardLayout(topLevelNames: ["PRIVATE"]))
        XCTAssertFalse(CardVolume.hasCardLayout(topLevelNames: ["Photos", "Movies"]))
    }

    /// The boot disk's /private is not a Sony card's PRIVATE.
    func testLowercasePrivateIsNotACardLayout() {
        XCTAssertFalse(CardVolume.hasCardLayout(topLevelNames: ["private", "Users", "System"]))
    }
}
