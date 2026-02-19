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

struct GyroflowConfig: Codable {
    var binary: String?
    var preset: GyroflowPreset?
}

struct GyroflowPreset: Codable {
    var stabilization: StabilizationSettings?
}

struct StabilizationSettings: Codable {
    var maxZoom: Double?
    var adaptiveZoomWindow: Double?
    var adaptiveZoomMethod: Int?

    enum CodingKeys: String, CodingKey {
        case maxZoom = "max_zoom"
        case adaptiveZoomWindow = "adaptive_zoom_window"
        case adaptiveZoomMethod = "adaptive_zoom_method"
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

struct MediaProfile: Codable, Identifiable {
    var id: String { name }

    var name: String = ""
    var type: MediaType?
    var sourceDir: String?
    var importDir: String?
    var readyDir: String?
    var backupEnabled: Bool?
    var backupDir: String?
    var backupExcludeSubdirs: [String]?
    var gyroflowEnabled: Bool?
    var tags: [String]?
    var exif: ExifConfig?
    var fileExtensions: [String]?
    var companionExtensions: [String]?

    enum CodingKeys: String, CodingKey {
        case type
        case sourceDir = "source_dir"
        case importDir = "import_dir"
        case readyDir = "ready_dir"
        case backupEnabled = "backup_enabled"
        case backupDir = "backup_dir"
        case backupExcludeSubdirs = "backup_exclude_subdirs"
        case gyroflowEnabled = "gyroflow_enabled"
        case tags, exif
        case fileExtensions = "file_extensions"
        case companionExtensions = "companion_extensions"
    }
}

struct ExifConfig: Codable {
    var make: String?
    var model: String?
}
