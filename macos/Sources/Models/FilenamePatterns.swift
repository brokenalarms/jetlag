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

    static func hasParseableTimestamp(_ filename: String, scriptsDirectory: String) -> Bool {
        let patterns = loadPatterns(scriptsDirectory: scriptsDirectory)
        let stem = (filename as NSString).deletingPathExtension
        let range = NSRange(stem.startIndex..., in: stem)
        return patterns.contains { $0.firstMatch(in: stem, range: range) != nil }
    }
}
