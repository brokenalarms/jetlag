import Foundation

struct ProfilesConfig: Codable {
    var gyroflow: GyroflowConfig?
    var backupConfig: BackupConfig?
    var profiles: [String: MediaProfile]

    enum CodingKeys: String, CodingKey {
        case gyroflow, profiles
        case backupConfig = "backup_config"
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

struct GyroflowConfig: Codable, Equatable {
    var binary: String?
    var preset: GyroflowPreset?
}

struct GyroflowPreset: Codable, Equatable {
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
    case disabled = 0
    case dynamic = 1
    case staticZoom = 2

    var id: Int { rawValue }

    var label: String {
        switch self {
        case .disabled: "Disabled"
        case .dynamic: "Dynamic"
        case .staticZoom: "Static"
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
    var gyroflowStabilization: StabilizationSettings?
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
        case gyroflowStabilization = "gyroflow_stabilization"
        case tags, exif
        case fileExtensions = "file_extensions"
        case companionExtensions = "companion_extensions"
    }
}

struct ExifConfig: Codable, Equatable {
    var make: String?
    var model: String?
}
