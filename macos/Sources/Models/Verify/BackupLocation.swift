import Foundation

/// A backup location: a mirror of the imported library, local or `host:/path`.
/// Stored in the profiles file's top-level `backups:` mapping, keyed by its name —
/// like a profile, the name is the key and not a field.
struct BackupLocationConfig: Codable, Equatable {
    var path: String

    enum CodingKeys: String, CodingKey, CaseIterable {
        case path
    }

    /// A `host:/path` root, listed by its host and never read across the network.
    var isRemote: Bool {
        guard !path.hasPrefix("/"), let colon = path.firstIndex(of: ":") else { return false }
        return !path[..<colon].contains("/")
    }

    /// Whether reading the location crosses a network: the Local/Network label.
    /// The scripts decide this again on every run from the mount table; this is the
    /// label shown before a run, from the volume's own local flag.
    var isNetwork: Bool {
        if isRemote { return true }
        let url = URL(fileURLWithPath: (path as NSString).expandingTildeInPath)
        let values = try? url.resourceValues(forKeys: [.volumeIsLocalKey])
        return values?.volumeIsLocal != true
    }
}

/// A backup location with the name it is stored under.
struct NamedBackupLocation: Identifiable, Equatable {
    let name: String
    let config: BackupLocationConfig
    var id: String { name }
}

/// The file lists the check sorts a card by: seeded once from the profiles'
/// extensions, then the check's own. Stored as the profiles file's `verify:` mapping.
struct VerifyListsConfig: Codable, Equatable {
    var mediaExtensions: [String]
    var companionExtensions: [String]
    var ignorePaths: [String]

    enum CodingKeys: String, CodingKey, CaseIterable {
        case mediaExtensions = "media_extensions"
        case companionExtensions = "companion_extensions"
        case ignorePaths = "ignore_paths"
    }

    /// Insta360 cards copy real clip names into MISC/ stubs that are not video.
    static let defaultIgnorePaths = ["MISC"]

    /// The lists seeded from every profile: their file types are media, and their
    /// companion types that are not also some profile's media are companions.
    static func seeded(from profiles: [String: MediaProfile]) -> VerifyListsConfig {
        func normalized(_ extensions: [String]?) -> [String] {
            (extensions ?? []).map { ($0.hasPrefix(".") ? $0 : ".\($0)").lowercased() }
        }
        let media = Set(profiles.values.flatMap { normalized($0.fileExtensions) })
        let companions = Set(profiles.values.flatMap { normalized($0.companionExtensions) })
            .subtracting(media)
        return VerifyListsConfig(mediaExtensions: media.sorted(),
                                 companionExtensions: companions.sorted(),
                                 ignorePaths: defaultIgnorePaths)
    }
}
