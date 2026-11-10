import Foundation
import Yams

/// The profiles file: the global gyroflow settings and every profile, keyed by
/// name.
///
/// `profiles` holds each profile as the file stores it. A gyroflow profile
/// that leaves a stabilization value unset follows the global preset, so it is
/// read through `profile(named:)`, which fills those values in, and written
/// back through `storable(_:replacing:)`, which leaves them unset again.
struct ProfilesConfig: Codable {
    var gyroflow: GyroflowConfig?
    var profiles: [String: MediaProfile]
    /// The whole file as it was read. A write is laid over it, so top-level and
    /// gyroflow keys the app does not model survive, as does the file's order.
    var fileNode: Node? = nil

    enum CodingKeys: String, CodingKey, CaseIterable {
        case gyroflow, profiles
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

    /// `profile`, edited from what `profile(named:)` showed, as it should be
    /// stored. A stabilization value still equal to what was shown for
    /// `original` is stored as `original` had it, so one that followed the global
    /// preset keeps following it rather than being pinned to today's value.
    func storable(_ profile: MediaProfile, replacing original: MediaProfile?) -> MediaProfile {
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
