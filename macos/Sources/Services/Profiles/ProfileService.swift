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
        var config: ProfilesConfig
        do {
            config = try decoder.decode(ProfilesConfig.self, from: yamlString)
        } catch let error as DecodingError {
            let detail: String
            switch error {
            case .typeMismatch(let type, let context):
                let path = context.codingPath.map(\.stringValue).joined(separator: " → ")
                detail = Strings.Errors.yamlTypeMismatch(path: path, expected: "\(type)")
            case .keyNotFound(let key, let context):
                let path = context.codingPath.map(\.stringValue).joined(separator: " → ")
                detail = Strings.Errors.yamlKeyMissing(key: key.stringValue, path: path)
            case .valueNotFound(let type, let context):
                let path = context.codingPath.map(\.stringValue).joined(separator: " → ")
                detail = Strings.Errors.yamlValueMissing(type: "\(type)", path: path)
            case .dataCorrupted(let context):
                let path = context.codingPath.map(\.stringValue).joined(separator: " → ")
                detail = path.isEmpty
                    ? context.debugDescription
                    : Strings.Errors.yamlInvalidAt(path: path, description: context.debugDescription)
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

        // The decode above succeeded, so the text is YAML; this keeps the file's
        // own tree so a save can be laid over it.
        ProfilesDocument.attach(try? Yams.compose(yaml: yamlString), to: &config)
        return config
    }

    /// Write `config` as an edit of the file it was read from: what the model
    /// holds replaces the file's, and everything else in the file is kept.
    static func write(_ config: ProfilesConfig, to path: String) throws {
        let url = URL(fileURLWithPath: (path as NSString).expandingTildeInPath)
        let encoded = try YAMLEncoder().encode(config)
        let yamlString: String
        if let written = try Yams.compose(yaml: encoded) {
            yamlString = try Yams.serialize(node: ProfilesDocument.merge(written, into: config))
        } else {
            yamlString = encoded
        }
        try yamlString.write(to: url, atomically: true, encoding: .utf8)
    }
}
