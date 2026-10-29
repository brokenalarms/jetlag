import XCTest
@testable import Jetlag

/// Looking for cards must never read the boot disk, a fixed drive or a network
/// share: those hold Photos, Desktop and other apps' data, or are guarded as a
/// whole, and reading them prompts for access.
final class CardVolumeTests: XCTestCase {

    func testBootDiskIsNeverACard() {
        XCTAssertFalse(CardVolume(isRootFileSystem: true, isLocal: true, isRemovable: true, isEjectable: true).mayBeCard)
    }

    func testFixedDriveIsNeverACard() {
        XCTAssertFalse(CardVolume(isRootFileSystem: false, isLocal: true, isRemovable: false, isEjectable: false).mayBeCard)
    }

    /// A mounted share reports itself ejectable; it is still never listed.
    func testNetworkShareIsNeverACard() {
        XCTAssertFalse(CardVolume(isRootFileSystem: false, isLocal: false, isRemovable: false, isEjectable: true).mayBeCard)
    }

    func testRemovableOrEjectableMediaMayBeACard() {
        XCTAssertTrue(CardVolume(isRootFileSystem: false, isLocal: true, isRemovable: true, isEjectable: false).mayBeCard)
        XCTAssertTrue(CardVolume(isRootFileSystem: false, isLocal: true, isRemovable: false, isEjectable: true).mayBeCard)
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
