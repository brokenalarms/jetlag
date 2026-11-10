import Foundation

/// One line of probe-camera's output: the camera a sample of one extension's
/// files carries, the kind of media they are, and how many sampled files
/// carried that camera.
struct ProbedCamera: Decodable, Equatable {
    let fileExtension: String
    let type: MediaType
    let files: Int
    let camera: FileCamera?

    private enum CodingKeys: String, CodingKey {
        case fileExtension = "extension"
        case type, files, make, model
    }

    init(fileExtension: String, type: MediaType, files: Int, camera: FileCamera?) {
        self.fileExtension = fileExtension
        self.type = type
        self.files = files
        self.camera = camera
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        fileExtension = try container.decode(String.self, forKey: .fileExtension)
        type = try container.decode(MediaType.self, forKey: .type)
        files = try container.decode(Int.self, forKey: .files)
        camera = FileCamera(
            make: try container.decodeIfPresent(String.self, forKey: .make),
            model: try container.decodeIfPresent(String.self, forKey: .model))
    }
}
