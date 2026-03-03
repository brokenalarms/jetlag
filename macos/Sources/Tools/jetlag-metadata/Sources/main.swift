import Foundation

@MainActor
struct MetadataService {
    private let exiftoolPath: String

    init() {
        let bundleDir = URL(fileURLWithPath: CommandLine.arguments[0])
            .deletingLastPathComponent().path
        let vendored = (bundleDir as NSString).appendingPathComponent("exiftool")
        if FileManager.default.isExecutableFile(atPath: vendored) {
            exiftoolPath = vendored
        } else {
            exiftoolPath = Self.findInPath("exiftool") ?? "exiftool"
        }
    }

    private static func findInPath(_ name: String) -> String? {
        guard let pathEnv = ProcessInfo.processInfo.environment["PATH"] else { return nil }
        for dir in pathEnv.split(separator: ":") {
            let candidate = "\(dir)/\(name)"
            if FileManager.default.isExecutableFile(atPath: candidate) {
                return candidate
            }
        }
        return nil
    }

    func readTags(file: String, tags: [String], fast: Bool) -> [String: String] {
        var args = ["-s"]
        if fast { args.append("-fast2") }
        args += tags.map { "-\($0)" }
        args.append(file)

        let output = runExifTool(args)
        var result: [String: String] = [:]
        for line in output.split(separator: "\n", omittingEmptySubsequences: true) {
            guard let colonIndex = line.firstIndex(of: ":") else { continue }
            let key = line[line.startIndex..<colonIndex]
                .trimmingCharacters(in: .whitespaces)
            let value = line[line.index(after: colonIndex)...]
                .trimmingCharacters(in: .whitespaces)
            if !key.isEmpty {
                result[key] = value
            }
        }
        return result
    }

    func writeTags(file: String, tags: [String: String]) -> (updated: Bool, filesChanged: Int) {
        var args = ["-P", "-overwrite_original"]
        for (key, value) in tags {
            args.append("-\(key)=\(value)")
        }
        args.append(file)

        let output = runExifTool(args)
        let pattern = /(\d+) image files? updated/
        if let match = output.firstMatch(of: pattern),
           let count = Int(match.1), count > 0 {
            return (true, count)
        }
        return (false, 0)
    }

    private func runExifTool(_ args: [String]) -> String {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: exiftoolPath)
        process.arguments = args

        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = Pipe()

        do {
            try process.run()
            process.waitUntilExit()
        } catch {
            return ""
        }

        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        return String(data: data, encoding: .utf8) ?? ""
    }
}

@MainActor
func main() {
    let service = MetadataService()

    while let line = readLine() {
        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { continue }

        guard let data = trimmed.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let op = json["op"] as? String,
              let file = json["file"] as? String
        else {
            print("{}")
            continue
        }

        switch op {
        case "read":
            guard let tags = json["tags"] as? [String] else {
                print("{}")
                continue
            }
            let fast = json["fast"] as? Bool ?? false
            let result = service.readTags(file: file, tags: tags, fast: fast)
            if let output = try? JSONSerialization.data(
                withJSONObject: result, options: [.sortedKeys]) {
                print(String(data: output, encoding: .utf8) ?? "{}")
            } else {
                print("{}")
            }

        case "write":
            guard let tags = json["tags"] as? [String: String] else {
                print("{}")
                continue
            }
            let (updated, filesChanged) = service.writeTags(file: file, tags: tags)
            let result: [String: Any] = ["updated": updated, "files_changed": filesChanged]
            if let output = try? JSONSerialization.data(
                withJSONObject: result, options: [.sortedKeys]) {
                print(String(data: output, encoding: .utf8) ?? "{}")
            } else {
                print("{}")
            }

        default:
            print("{}")
        }

        fflush(stdout)
    }
}

main()
