import Foundation

/// Whether the interpreter the scripts would resolve can actually run.
enum PythonRuntimeStatus: Equatable {
    case ready
    /// No developer directory is set, so `/usr/bin/python3` is the Command Line
    /// Tools shim: invoking it opens the install dialog instead of starting an
    /// interpreter.
    case commandLineToolsMissing
}

/// Mirrors the interpreter resolution in `scripts/lib/ensure-venv.sh` without
/// invoking anything — running `/usr/bin/python3` to see whether it works is
/// exactly what triggers the developer-tools install dialog.
struct PythonRuntimeCheck {
    /// `xcode-select -p` exits nonzero when no developer directory is set.
    var developerDirectoryPresent: () -> Bool
    /// `JETLAG_PYTHON`, resolved first by ensure-venv.sh.
    var overrideInterpreter: () -> String?
    /// A `python3` on PATH outside `/usr/bin`, ensure-venv.sh's last fallback.
    var pathInterpreter: () -> String?

    var status: PythonRuntimeStatus {
        if overrideInterpreter() != nil { return .ready }
        if developerDirectoryPresent() { return .ready }
        if pathInterpreter() != nil { return .ready }
        return .commandLineToolsMissing
    }

    static let system = PythonRuntimeCheck(
        developerDirectoryPresent: {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/xcode-select")
            process.arguments = ["-p"]
            process.standardOutput = FileHandle.nullDevice
            process.standardError = FileHandle.nullDevice
            do {
                try process.run()
            } catch {
                return false
            }
            process.waitUntilExit()
            return process.terminationStatus == 0
        },
        overrideInterpreter: {
            let path = ProcessInfo.processInfo.environment["JETLAG_PYTHON"] ?? ""
            return FileManager.default.isExecutableFile(atPath: path) ? path : nil
        },
        pathInterpreter: {
            let searchPath = ProcessInfo.processInfo.environment["PATH"] ?? ""
            for directory in searchPath.split(separator: ":") where directory != "/usr/bin" {
                let candidate = (String(directory) as NSString).appendingPathComponent("python3")
                if FileManager.default.isExecutableFile(atPath: candidate) {
                    return candidate
                }
            }
            return nil
        }
    )
}
