import Foundation

/// Where an installed Gyroflow was found, as reported by download-gyroflow.sh.
enum GyroflowSource: String {
    case applications
    case jetlagTools = "jetlag-tools"
    case path
    case configured
}

/// Whether Gyroflow is installed on this machine, and where.
///
/// Gyroflow is not shipped inside Jetlag.app — its CLI only runs from inside a
/// real Gyroflow.app, so the app is installed alongside Jetlag instead.
/// `isInstalled` is the single flag every gyroflow feature is gated on.
struct GyroflowStatus: Equatable {
    var isInstalled: Bool = false
    var path: String?
    var source: GyroflowSource?

    static let notInstalled = GyroflowStatus()

    /// Read the `@@present` / `@@path` / `@@source` data download-gyroflow.sh
    /// writes to stdout, ignoring any progress output around it.
    static func parse(_ output: String) -> GyroflowStatus {
        var fields: [String: String] = [:]
        for line in output.split(separator: "\n", omittingEmptySubsequences: true) {
            guard line.hasPrefix("@@") else { continue }
            let body = line.dropFirst(2)
            guard let separator = body.firstIndex(of: "=") else { continue }
            fields[String(body[body.startIndex..<separator])] = String(body[body.index(after: separator)...])
        }

        guard fields["present"] == "true" else { return .notInstalled }
        return GyroflowStatus(
            isInstalled: true,
            path: fields["path"],
            source: fields["source"].flatMap(GyroflowSource.init(rawValue:))
        )
    }

    var displayName: String {
        switch source {
        case .applications: return Strings.Settings.gyroflowSourceApplications
        case .jetlagTools: return Strings.Settings.gyroflowSourceJetlag
        case .path: return Strings.Settings.gyroflowSourcePath
        case .configured, nil: return path ?? ""
        }
    }
}
