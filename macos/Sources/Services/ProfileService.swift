import Foundation
import Yams

struct ProfileLoadError: Error {
    let message: String
    let filePath: String
    let detail: String?

    var displayMessage: String {
        if let detail {
            return "\(message): \(detail)"
        }
        return message
    }
}

struct ProfileService {
    static func load(from path: String) throws(ProfileLoadError) -> ProfilesConfig {
        let resolved = (path as NSString).expandingTildeInPath
        let url = URL(fileURLWithPath: resolved)

        guard FileManager.default.fileExists(atPath: url.path) else {
            throw ProfileLoadError(
                message: Strings.Errors.profilesNotFound,
                filePath: resolved,
                detail: nil
            )
        }

        let yamlString: String
        do {
            yamlString = try String(contentsOf: url, encoding: .utf8)
        } catch {
            throw ProfileLoadError(
                message: Strings.Errors.profilesUnreadable,
                filePath: resolved,
                detail: error.localizedDescription
            )
        }

        let decoder = YAMLDecoder()
        let config: ProfilesConfig
        do {
            config = try decoder.decode(ProfilesConfig.self, from: yamlString)
        } catch let error as DecodingError {
            let detail: String
            switch error {
            case .typeMismatch(let type, let context):
                let path = context.codingPath.map(\.stringValue).joined(separator: " → ")
                detail = "Type mismatch at \(path): expected \(type)"
            case .keyNotFound(let key, let context):
                let path = context.codingPath.map(\.stringValue).joined(separator: " → ")
                detail = "Missing key '\(key.stringValue)' at \(path)"
            case .valueNotFound(let type, let context):
                let path = context.codingPath.map(\.stringValue).joined(separator: " → ")
                detail = "Missing value of type \(type) at \(path)"
            case .dataCorrupted(let context):
                let path = context.codingPath.map(\.stringValue).joined(separator: " → ")
                detail = path.isEmpty ? context.debugDescription : "At \(path): \(context.debugDescription)"
            @unknown default:
                detail = error.localizedDescription
            }
            throw ProfileLoadError(
                message: Strings.Errors.profilesInvalidYAML,
                filePath: resolved,
                detail: detail
            )
        } catch {
            throw ProfileLoadError(
                message: Strings.Errors.profilesParseFailed,
                filePath: resolved,
                detail: error.localizedDescription
            )
        }

        return config
    }

    static func write(_ config: ProfilesConfig, to path: String) throws {
        let url = URL(fileURLWithPath: (path as NSString).expandingTildeInPath)
        let encoder = YAMLEncoder()
        let yamlString = try encoder.encode(config)
        try yamlString.write(to: url, atomically: true, encoding: .utf8)
    }
}
