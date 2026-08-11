import Foundation
import Observation

@Observable
final class LicenseStore {
    static let shared = LicenseStore()

    private static let unlockedKey = "jetlag.pro.unlocked"

    var isUnlocked: Bool {
        didSet { UserDefaults.standard.set(isUnlocked, forKey: Self.unlockedKey) }
    }

    private init() {
        #if DEBUG
        // Set by the Jetlag scheme so a debug run is never gated. Assigning in
        // init skips didSet, so the override stays for this run only. Release
        // builds cannot be unlocked this way.
        if let override = ProcessInfo.processInfo.environment["JETLAG_PRO_UNLOCKED"] {
            isUnlocked = (override as NSString).boolValue
            return
        }
        #endif
        isUnlocked = UserDefaults.standard.bool(forKey: Self.unlockedKey)
    }

    /// Maximum files per run. Free tier: 50. Unlocked: unlimited.
    var fileLimit: Int { isUnlocked ? Int.max : 50 }

    func exceedsLimit(fileCount: Int) -> Bool {
        fileCount > fileLimit
    }

    // MARK: - Stub activation (replace with Paddle/Stripe integration)

    var isActivating: Bool = false
    var activationError: String?

    func activate(licenseKey: String) async {
        isActivating = true
        activationError = nil
        defer { isActivating = false }

        // Simulate network latency so the UI feels responsive
        try? await Task.sleep(for: .seconds(1))

        // Stub: always fails until real payment integration is wired
        activationError = Strings.Errors.licenseComingSoon
    }
}
