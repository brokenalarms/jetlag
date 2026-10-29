import Foundation

struct FilenamePattern: Decodable {
    let regex: String
    let name: String
    let hasTime: Bool

    private enum CodingKeys: String, CodingKey {
        case regex, name
        case hasTime = "has_time"
    }
}

enum FilenamePatterns {
    private static func loadPatterns(scriptsDirectory: String) -> [NSRegularExpression] {
        let path = (scriptsDirectory as NSString)
            .appendingPathComponent("lib/filename-patterns.json")
        guard let data = FileManager.default.contents(atPath: path),
              let decoded = try? JSONDecoder().decode([FilenamePattern].self, from: data)
        else { return [] }
        return decoded.compactMap { try? NSRegularExpression(pattern: $0.regex) }
    }

    private static func hasParseableTimestamp(_ filename: String, patterns: [NSRegularExpression]) -> Bool {
        let stem = (filename as NSString).deletingPathExtension
        let range = NSRange(stem.startIndex..., in: stem)
        return patterns.contains { $0.firstMatch(in: stem, range: range) != nil }
    }

    /// Whether any file of the given types under source has a timestamp in its
    /// name. One walk, ending at the first such file, off the main thread and
    /// abandoned when the task is cancelled. Hidden entries and packages are not
    /// read: a Photos library inside the source would prompt for Photos access.
    static func sourceHasTimestampedNames(
        _ source: String, extensions: [String], scriptsDirectory: String
    ) async -> Bool {
        walkForTimestampedName(source, extensions: extensions, scriptsDirectory: scriptsDirectory,
                               isCancelled: { Task.isCancelled })
    }

    private static func walkForTimestampedName(
        _ source: String, extensions: [String], scriptsDirectory: String, isCancelled: () -> Bool
    ) -> Bool {
        let wanted = Set(extensions.map {
            $0.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "."))
        })
        guard !source.isEmpty, !wanted.isEmpty,
              let enumerator = FileManager.default.enumerator(
                  at: URL(fileURLWithPath: source),
                  includingPropertiesForKeys: nil,
                  options: [.skipsHiddenFiles, .skipsPackageDescendants])
        else { return false }
        let patterns = loadPatterns(scriptsDirectory: scriptsDirectory)
        for case let url as URL in enumerator {
            if isCancelled() { return false }
            if wanted.contains(url.pathExtension.lowercased()),
               hasParseableTimestamp(url.lastPathComponent, patterns: patterns) {
                return true
            }
        }
        return false
    }
}
