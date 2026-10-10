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
        // Assigning in init skips didSet, so an environment override stays for
        // this run only.
        isUnlocked = Self.initialUnlocked(
            environment: ProcessInfo.processInfo.environment,
            defaults: .standard
        )
    }

    static func initialUnlocked(environment: [String: String], defaults: UserDefaults) -> Bool {
        #if DEBUG
        // The Jetlag scheme sets JETLAG_PRO_UNLOCKED, but the scheme is a
        // generated, untracked file that can be missing — so a debug build with
        // no stored choice also starts unlocked rather than depending on how it
        // was launched. Release builds cannot be unlocked this way.
        if let override = environment["JETLAG_PRO_UNLOCKED"] {
            return (override as NSString).boolValue
        }
        return defaults.object(forKey: unlockedKey) as? Bool ?? true
        #else
        return defaults.bool(forKey: unlockedKey)
        #endif
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
