import Foundation

/// Where the profiles file the app reads and writes lives.
///
/// The copy inside the app bundle is the shipped default and is only ever read:
/// the `Bundle scripts` build phase replaces it on every build, and an installed,
/// signed app cannot write into its own bundle at all. The live file is seeded
/// from that copy once and then belongs to the user.
struct ProfilesLocation {
    static let fileName = "media-profiles.yaml"

    /// The variable `scripts/lib/profiles.py` reads in preference to its own
    /// `<scripts>/media-profiles.yaml` default, so scripts launched by the app
    /// read the same file the app writes.
    static let environmentKey = "JETLAG_PROFILES_FILE"

    /// Directory holding the live, user-owned profiles file.
    let directory: String

    /// The read-only copy shipped in the app bundle, used to seed `path` once.
    let seedPath: String

    var path: String {
        (directory as NSString).appendingPathComponent(Self.fileName)
    }

    static func userDomain(
        scriptsDirectory: String,
        bundle: Bundle = .main,
        fileManager: FileManager = .default
    ) -> ProfilesLocation {
        ProfilesLocation(
            directory: applicationSupportDirectory(bundle: bundle, fileManager: fileManager),
            seedPath: (scriptsDirectory as NSString).appendingPathComponent(fileName)
        )
    }

    /// The app names its folder after itself as the bundle presents it, so a
    /// build carrying a distinct identity — `Jetlag Dev` out of a worktree —
    /// keeps its profiles apart from the installed app's rather than editing
    /// them. The bundle id's last component covers a bundle with no display
    /// name, and the bundle's own file name is the last resort.
    static func applicationSupportFolderName(bundle: Bundle = .main) -> String {
        if let name = bundle.object(forInfoDictionaryKey: kCFBundleNameKey as String) as? String,
           !name.isEmpty {
            return name
        }
        if let identifierTail = bundle.bundleIdentifier?.split(separator: ".").last,
           !identifierTail.isEmpty {
            return String(identifierTail)
        }
        return bundle.bundleURL.deletingPathExtension().lastPathComponent
    }

    static func applicationSupportDirectory(
        bundle: Bundle = .main,
        fileManager: FileManager = .default
    ) -> String {
        let base = fileManager
            .urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? URL(fileURLWithPath: NSHomeDirectory(), isDirectory: true)
                .appendingPathComponent("Library/Application Support", isDirectory: true)
        return base
            .appendingPathComponent(applicationSupportFolderName(bundle: bundle), isDirectory: true)
            .path
    }

    /// Put the shipped defaults in place the first time the app runs, creating
    /// the directory on demand. Reports whether the copy happened — a file that
    /// is already there is the user's and is never overwritten.
    @discardableResult
    func seedIfNeeded(fileManager: FileManager = .default) throws -> Bool {
        guard !fileManager.fileExists(atPath: path),
              fileManager.fileExists(atPath: seedPath)
        else { return false }

        try fileManager.createDirectory(
            atPath: directory, withIntermediateDirectories: true)
        try fileManager.copyItem(atPath: seedPath, toPath: path)
        return true
    }
}
