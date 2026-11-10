import Foundation
import Yams

struct GyroflowConfig: Codable {
    var binary: String?
    var preset: GyroflowPreset?

    enum CodingKeys: String, CodingKey, CaseIterable {
        case binary, preset
    }
}

struct GyroflowPreset: Codable {
    var stabilization: StabilizationSettings?

    enum CodingKeys: String, CodingKey, CaseIterable {
        case stabilization
    }
}

struct StabilizationSettings: Codable, Equatable {
    var maxZoom: Double?
    var adaptiveZoomWindow: Double?
    var adaptiveZoomMethod: Int?

    enum CodingKeys: String, CodingKey, CaseIterable {
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
    var gyroflowEnabled: Bool?
    var gyroflowSettings: StabilizationSettings?
    var tags: [String]?
    var exif: ExifConfig?
    var fileExtensions: [String]?
    var companionExtensions: [String]?
    /// The profile's block as it was read from the profiles file. A save is
    /// written over it, so keys the app does not model — or anything a newer
    /// script reads — survive a save, a rename and a copy.
    var fileNode: Node? = nil

    enum CodingKeys: String, CodingKey, CaseIterable {
        case type
        case sourceDir = "source_dir"
        case readyDir = "ready_dir"
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

    enum CodingKeys: String, CodingKey, CaseIterable {
        case make, model
    }
}
