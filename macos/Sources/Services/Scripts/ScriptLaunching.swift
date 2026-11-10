import Foundation

/// Starts one of the bundled scripts and streams its output, line by line.
///
/// Every script the app runs goes through the launcher `AppState` holds, so a
/// test can stand in a launcher that replays recorded output instead of
/// spawning anything.
protocol ScriptLaunching {
    func run(script: String, args: [String]) -> (process: ScriptProcess, stream: AsyncStream<LogLine>)
}

/// Runs scripts from the scripts directory against the user's profiles file.
struct LiveScriptLauncher: ScriptLaunching {
    let scriptsDirectory: String
    let profilesPath: String

    func run(script: String, args: [String]) -> (process: ScriptProcess, stream: AsyncStream<LogLine>) {
        ScriptRunner.run(
            script: script,
            args: args,
            workingDir: scriptsDirectory,
            profilesPath: profilesPath
        )
    }
}
