import Foundation
import Observation

@Observable
final class LicenseStore {
    static let shared = LicenseStore()

    private let unlockedKey = "jetlag.pro.unlocked"

    var isUnlocked: Bool {
        get { UserDefaults.standard.bool(forKey: unlockedKey) }
        set { UserDefaults.standard.set(newValue, forKey: unlockedKey) }
    }

    /// Maximum files per run. Free tier: 50. Unlocked: unlimited.
    var fileLimit: Int { isUnlocked ? Int.max : 50 }

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
