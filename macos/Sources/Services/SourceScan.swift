import Foundation

/// Asks scan-source what a source holds, so the media count and the filename-date
/// check are answered by the scripts that define media files and filename dates.
enum SourceScan {
    private struct Count: Decodable {
        let mediaFiles: Int
        enum CodingKeys: String, CodingKey { case mediaFiles = "media_files" }
    }

    private struct TimestampedNames: Decodable {
        let hasTimestampedNames: Bool
        enum CodingKeys: String, CodingKey { case hasTimestampedNames = "has_timestamped_names" }
    }

    static func mediaFileCount(source: String, extensions: [String],
                               scriptsDirectory: String, profilesPath: String) async -> Int? {
        await scan(Count.self, flag: "--count", source: source, extensions: extensions,
                   scriptsDirectory: scriptsDirectory, profilesPath: profilesPath)?.mediaFiles
    }

    static func hasTimestampedNames(source: String, extensions: [String],
                                    scriptsDirectory: String, profilesPath: String) async -> Bool {
        await scan(TimestampedNames.self, flag: "--timestamped-names", source: source, extensions: extensions,
                   scriptsDirectory: scriptsDirectory, profilesPath: profilesPath)?.hasTimestampedNames ?? false
    }

    private static func scan<Result: Decodable>(
        _ type: Result.Type, flag: String, source: String, extensions: [String],
        scriptsDirectory: String, profilesPath: String
    ) async -> Result? {
        guard !source.isEmpty, !extensions.isEmpty else { return nil }
        let (process, stream) = ScriptRunner.run(
            script: "scan-source.sh",
            args: [source, flag, "--extensions"] + extensions,
            workingDir: scriptsDirectory,
            profilesPath: profilesPath
        )
        return await withTaskCancellationHandler {
            var result: Result?
            for await line in stream where line.stream == .stdout && line.isMachineReadable {
                if let data = line.text.data(using: .utf8),
                   let decoded = try? JSONDecoder().decode(Result.self, from: data) {
                    result = decoded
                }
            }
            process.waitUntilExit()
            return result
        } onCancel: {
            process.terminateGroup()
        }
    }
}
