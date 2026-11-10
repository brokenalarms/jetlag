import Foundation
import Yams

/// The profiles file: the global gyroflow settings and every profile, keyed by
/// name.
///
/// `profiles` holds each profile as the file stores it. A gyroflow profile
/// that leaves a stabilization value unset follows the global preset, so it is
/// read through `profile(named:)`, which fills those values in, and written
/// back through `save(_:as:replacing:)`, which leaves them unset again.
struct ProfilesConfig: Codable {
    var gyroflow: GyroflowConfig?
    var profiles: [String: MediaProfile]
    /// The whole file as it was read. A write is laid over it, so top-level and
    /// gyroflow keys the app does not model survive, as does the file's order.
    var fileNode: Node? = nil
    /// Backup locations verify-card checks a card against, keyed by name.
    var backups: [String: BackupLocationConfig]? = nil
    /// The check's file lists; seeded from the profiles until first saved.
    var verify: VerifyListsConfig? = nil

    enum CodingKeys: String, CodingKey, CaseIterable {
        case gyroflow, profiles, backups, verify
    }

    /// The lists verify-card sorts a card by: the saved ones, or seeded from the
    /// profiles when none have been saved.
    var verifyLists: VerifyListsConfig {
        verify ?? VerifyListsConfig.seeded(from: profiles)
    }

    /// Backup locations by name, in name order.
    var sortedBackups: [NamedBackupLocation] {
        (backups ?? [:]).sorted { $0.key < $1.key }.map { NamedBackupLocation(name: $0.key, config: $0.value) }
    }

    var globalStabilization: StabilizationSettings? {
        gyroflow?.preset?.stabilization
    }

    /// The profile as the app shows and runs it.
    func profile(named name: String) -> MediaProfile? {
        profiles[name].map { normalized($0) }
    }

    /// A gyroflow profile with every stabilization value it leaves unset taken
    /// from the global preset.
    func normalized(_ profile: MediaProfile) -> MediaProfile {
        guard profile.gyroflowEnabled == true else { return profile }
        var result = profile
        result.gyroflowSettings = Self.filled(profile.gyroflowSettings, from: globalStabilization)
        return result
    }

    func normalized() -> ProfilesConfig {
        var result = self
        result.profiles = profiles.mapValues { normalized($0) }
        return result
    }

    /// Store `profile`, edited from what `profile(named:)` showed, under `name`.
    /// `storedName` is the name it is stored under now — nil for a profile never
    /// saved — and saving under another name is a rename. Another profile that
    /// already has `name` is never replaced: the save is refused instead.
    mutating func save(_ profile: MediaProfile, as name: String, replacing storedName: String?) throws {
        if name != storedName, profiles[name] != nil {
            throw ProfileNameError.taken(name)
        }
        let original = storedName.flatMap { profiles[$0] }
        if let storedName, storedName != name {
            profiles.removeValue(forKey: storedName)
        }
        profiles[name] = storable(profile, replacing: original)
    }

    mutating func remove(named name: String) {
        profiles.removeValue(forKey: name)
    }

    /// `base` when no profile has that name, otherwise the first free one of
    /// `base 2`, `base 3`, …
    func uniqueName(_ base: String) -> String {
        guard profiles[base] != nil else { return base }
        var counter = 2
        while profiles["\(base) \(counter)"] != nil {
            counter += 1
        }
        return "\(base) \(counter)"
    }

    /// `profile` as it should be stored. A stabilization value still equal to
    /// what was shown for `original` is stored as `original` had it, so one that
    /// followed the global preset keeps following it rather than being pinned to
    /// today's value.
    private func storable(_ profile: MediaProfile, replacing original: MediaProfile?) -> MediaProfile {
        guard profile.gyroflowEnabled == true, let edited = profile.gyroflowSettings else { return profile }
        let stored = original?.gyroflowSettings
        let shown = Self.filled(stored, from: globalStabilization)
        let kept = StabilizationSettings(
            maxZoom: edited.maxZoom == shown.maxZoom
                ? stored?.maxZoom : edited.maxZoom,
            adaptiveZoomWindow: edited.adaptiveZoomWindow == shown.adaptiveZoomWindow
                ? stored?.adaptiveZoomWindow : edited.adaptiveZoomWindow,
            adaptiveZoomMethod: edited.adaptiveZoomMethod == shown.adaptiveZoomMethod
                ? stored?.adaptiveZoomMethod : edited.adaptiveZoomMethod)
        var result = profile
        result.gyroflowSettings = stored == nil && kept == StabilizationSettings() ? nil : kept
        return result
    }

    private static func filled(
        _ settings: StabilizationSettings?, from global: StabilizationSettings?
    ) -> StabilizationSettings {
        StabilizationSettings(
            maxZoom: settings?.maxZoom ?? global?.maxZoom,
            adaptiveZoomWindow: settings?.adaptiveZoomWindow ?? global?.adaptiveZoomWindow,
            adaptiveZoomMethod: settings?.adaptiveZoomMethod ?? global?.adaptiveZoomMethod)
    }
}

/// Why a profile could not be saved under the name given.
enum ProfileNameError: LocalizedError, Equatable {
    /// Another profile already has the name; saving would replace it.
    case taken(String)

    var errorDescription: String? {
        switch self {
        case .taken(let name): return Strings.Profiles.nameTakenMessage(name)
        }
    }
}
