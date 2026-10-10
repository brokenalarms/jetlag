import XCTest
@testable import Jetlag

/// A debug build must never gate the developer's own runs, however it was
/// launched — the scheme that carries JETLAG_PRO_UNLOCKED is generated and
/// untracked, so it can be missing.
final class LicenseStoreTests: XCTestCase {

    private var defaults: UserDefaults!
    private var suiteName: String!

    override func setUp() {
        super.setUp()
        suiteName = "LicenseStoreTests.\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suiteName)
    }

    override func tearDown() {
        defaults.removePersistentDomain(forName: suiteName)
        super.tearDown()
    }

    func testDebugBuildWithNoSchemeAndNoStoredChoiceIsUnlocked() {
        XCTAssertTrue(LicenseStore.initialUnlocked(environment: [:], defaults: defaults))
    }

    func testStoredDebugToggleChoiceIsHonoured() {
        defaults.set(false, forKey: "jetlag.pro.unlocked")
        XCTAssertFalse(LicenseStore.initialUnlocked(environment: [:], defaults: defaults))
    }

    func testEnvironmentOverrideBeatsStoredChoice() {
        defaults.set(true, forKey: "jetlag.pro.unlocked")
        XCTAssertFalse(LicenseStore.initialUnlocked(
            environment: ["JETLAG_PRO_UNLOCKED": "0"],
            defaults: defaults
        ))
    }
}
