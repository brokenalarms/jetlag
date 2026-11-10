import XCTest
@testable import Jetlag

/// A developer build (Debug, or the Release app `make` builds for this Mac) must
/// never gate the developer's own runs, however it was launched — the scheme
/// that carries JETLAG_PRO_UNLOCKED is generated and untracked, so it can be
/// missing. The shipping build must keep the free-tier limit regardless.
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

    /// The free tier stops a run of more than 50 files. Unlocking lifts the limit,
    /// and the choice is kept in the store's own defaults, not the app's.
    func testFreeTierLimitsARunUntilUnlocked() {
        let store = LicenseStore(defaults: defaults, environment: [:], developerBuild: false)

        XCTAssertFalse(store.exceedsLimit(fileCount: 50))
        XCTAssertTrue(store.exceedsLimit(fileCount: 51))

        store.isUnlocked = true

        XCTAssertFalse(store.exceedsLimit(fileCount: 10_000))
        XCTAssertTrue(defaults.bool(forKey: "jetlag.pro.unlocked"))
    }

    /// The build customers get cannot be unlocked by an environment variable,
    /// and starts on the free tier.
    func testShippingBuildIgnoresEnvironmentAndStartsLocked() {
        XCTAssertFalse(LicenseStore.initialUnlocked(
            environment: ["JETLAG_PRO_UNLOCKED": "1"],
            defaults: defaults,
            developerBuild: false
        ))
    }

    /// The website states the free-tier limit from design/product.json; the app
    /// must enforce the same number.
    func testFreeFileLimitMatchesTheProductFacts() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // Services
            .deletingLastPathComponent()   // Tests
            .deletingLastPathComponent()   // macos
            .deletingLastPathComponent()   // repo root
            .appendingPathComponent("design/product.json")
        let product = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any]
        let limit = try XCTUnwrap(product?["freeFileLimit"] as? Int, "design/product.json has no freeFileLimit")
        XCTAssertEqual(LicenseStore.freeFileLimit, limit)
    }
}
