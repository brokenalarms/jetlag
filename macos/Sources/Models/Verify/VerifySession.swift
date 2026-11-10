import Foundation

/// The Verify screen's choices and its last check.
struct VerifySession {
    var source: String = ""
    /// Names of the backup locations included in this check.
    var enabledLocations: Set<String> = []
    var includeCompanions = false
    var verifyHashes = false
    var includeNetwork = false
    var showMatched = false

    var isRunning = false
    var report = VerifyReport()
    /// verify-card's own lines, for a check that could not run.
    var log: [LogLine] = []

    /// verify-card's arguments for the locations enabled, in the file's order.
    static func arguments(source: String, locations: [NamedBackupLocation],
                          lists: VerifyListsConfig, includeCompanions: Bool,
                          verifyHashes: Bool, includeNetwork: Bool) -> [String] {
        var args = [source]
        for location in locations {
            args += ["--location", "\(location.name)=\(location.config.path)"]
        }
        args += ["--media-extensions"] + lists.mediaExtensions
        if !lists.companionExtensions.isEmpty {
            args += ["--companion-extensions"] + lists.companionExtensions
        }
        if includeCompanions {
            args.append("--include-companions")
        }
        if !lists.ignorePaths.isEmpty {
            args += ["--ignore-paths"] + lists.ignorePaths
        }
        if verifyHashes {
            args.append("--verify-hashes")
            if includeNetwork {
                args.append("--include-network")
            }
        }
        return args
    }
}
