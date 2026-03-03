import Foundation

struct ProfilesConfig: Codable {
    var gyroflow: GyroflowConfig?
    var backupConfig: BackupConfig?
    var profiles: [String: MediaProfile]

    enum CodingKeys: String, CodingKey {
        case gyroflow, profiles
        case backupConfig = "backup_config"
    }

    func normalized() -> ProfilesConfig {
        let globalStab = gyroflow?.preset?.stabilization
        var result = self
        for (name, profile) in profiles {
            guard profile.gyroflowEnabled == true else { continue }
            var p = profile
            if p.gyroflowSettings == nil {
                p.gyroflowSettings = globalStab ?? StabilizationSettings()
            } else if let globalStab {
                var settings = p.gyroflowSettings!
                settings.maxZoom = settings.maxZoom ?? globalStab.maxZoom
                settings.adaptiveZoomWindow = settings.adaptiveZoomWindow ?? globalStab.adaptiveZoomWindow
                settings.adaptiveZoomMethod = settings.adaptiveZoomMethod ?? globalStab.adaptiveZoomMethod
                p.gyroflowSettings = settings
            }
            result.profiles[name] = p
        }
        return result
    }
}

struct BackupConfig: Codable {
    var localBasePath: String?
    var remoteBasePath: String?

    enum CodingKeys: String, CodingKey {
        case localBasePath = "local_base_path"
        case remoteBasePath = "remote_base_path"
    }
}

struct GyroflowConfig: Codable {
    var binary: String?
    var preset: GyroflowPreset?
}

struct GyroflowPreset: Codable {
    var stabilization: StabilizationSettings?
}

struct StabilizationSettings: Codable, Equatable {
    var maxZoom: Double?
    var adaptiveZoomWindow: Double?
    var adaptiveZoomMethod: Int?

    enum CodingKeys: String, CodingKey {
        case maxZoom = "max_zoom"
        case adaptiveZoomWindow = "adaptive_zoom_window"
        case adaptiveZoomMethod = "adaptive_zoom_method"
    }
}

enum AdaptiveZoomMethod: Int, CaseIterable, Identifiable {
    case none = 0
    case dynamic = 1
    case `static` = 2

    var id: Int { rawValue }

    var label: String {
        switch self {
        case .none: Strings.Profiles.zoomMethodNone
        case .dynamic: Strings.Profiles.zoomMethodDynamic
        case .static: Strings.Profiles.zoomMethodStatic
        }
    }
}

enum MediaType: String, Codable, CaseIterable, Identifiable {
    case video
    case photo

    var id: String { rawValue }

    var label: String {
        switch self {
        case .video: "Video"
        case .photo: "Photo"
        }
    }

    var systemImage: String {
        switch self {
        case .video: "video"
        case .photo: "photo"
        }
    }
}

struct MediaProfile: Codable, Equatable {
    var type: MediaType?
    var sourceDir: String?
    var readyDir: String?
    var backupEnabled: Bool?
    var backupDir: String?
    var backupExcludeSubdirs: [String]?
    var gyroflowEnabled: Bool?
    var gyroflowSettings: StabilizationSettings?
    var tags: [String]?
    var exif: ExifConfig?
    var fileExtensions: [String]?
    var companionExtensions: [String]?

    enum CodingKeys: String, CodingKey {
        case type
        case sourceDir = "source_dir"
        case readyDir = "ready_dir"
        case backupEnabled = "backup_enabled"
        case backupDir = "backup_dir"
        case backupExcludeSubdirs = "backup_exclude_subdirs"
        case gyroflowEnabled = "gyroflow_enabled"
        case gyroflowSettings = "gyroflow_settings"
        case tags, exif
        case fileExtensions = "file_extensions"
        case companionExtensions = "companion_extensions"
    }
}

struct ExifConfig: Codable, Equatable {
    var make: String?
    var model: String?
}
