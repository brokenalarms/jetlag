import Foundation

struct ReadRequest: Decodable {
    let file: String
    let tags: [String]
    let fast: Bool?
}

struct WriteRequest: Decodable {
    let file: String
    let tags: [String: String]
}

struct Request: Decodable {
    let op: String
    let file: String
    let tags: AnyCodable
    let fast: Bool?
}

enum AnyCodable: Decodable {
    case array([String])
    case dictionary([String: String])

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let arr = try? container.decode([String].self) {
            self = .array(arr)
            return
        }
        if let dict = try? container.decode([String: String].self) {
            self = .dictionary(dict)
            return
        }
        throw DecodingError.typeMismatch(
            AnyCodable.self,
            DecodingError.Context(codingPath: decoder.codingPath, debugDescription: "Expected array or dictionary")
        )
    }
}

final class ExifToolBackend {
    private var process: Process?
    private var stdin: FileHandle?
    private var stdout: FileHandle?
    private var execId = 0
    private let lock = NSLock()

    func ensureRunning() throws {
        if let p = process, p.isRunning { return }

        let exiftoolPath = resolveExifToolPath()

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: exiftoolPath)
        proc.arguments = ["-stay_open", "True", "-@", "-"]

        let stdinPipe = Pipe()
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()

        proc.standardInput = stdinPipe
        proc.standardOutput = stdoutPipe
        proc.standardError = stderrPipe

        try proc.run()

        self.process = proc
        self.stdin = stdinPipe.fileHandleForWriting
        self.stdout = stdoutPipe.fileHandleForReading
    }

    private func resolveExifToolPath() -> String {
        let execURL = URL(fileURLWithPath: ProcessInfo.processInfo.arguments[0])
        let toolsDir = execURL.deletingLastPathComponent()

        let siblingPath = toolsDir.appendingPathComponent("exiftool").path
        if FileManager.default.isExecutableFile(atPath: siblingPath) {
            return siblingPath
        }

        let scriptToolsDir = toolsDir
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("tools")
            .appendingPathComponent("exiftool")
        if FileManager.default.isExecutableFile(atPath: scriptToolsDir.path) {
            return scriptToolsDir.path
        }

        return "exiftool"
    }

    func execute(_ args: [String]) throws -> String {
        lock.lock()
        defer { lock.unlock() }

        try ensureRunning()
        guard let stdinHandle = stdin, let stdoutHandle = stdout else {
            throw MetadataError.notRunning
        }

        execId += 1
        let sentinel = "{ready\(execId)}"

        let payload = args.joined(separator: "\n") + "\n-execute\(execId)\n"
        stdinHandle.write(payload.data(using: .utf8)!)

        var lines: [String] = []
        var buffer = Data()

        while true {
            let chunk = stdoutHandle.availableData
            if chunk.isEmpty { break }
            buffer.append(chunk)

            while let range = buffer.range(of: Data("\n".utf8)) {
                let lineData = buffer[buffer.startIndex..<range.lowerBound]
                buffer.removeSubrange(buffer.startIndex...range.lowerBound)
                let line = String(data: lineData, encoding: .utf8)?.trimmingCharacters(in: .carriageReturns) ?? ""
                if line == sentinel {
                    return lines.joined(separator: "\n")
                }
                lines.append(line)
            }
        }

        return lines.joined(separator: "\n")
    }

    func readTags(file: String, tags: [String], fast: Bool) throws -> [String: String] {
        var args = ["-s"]
        if fast { args.append("-fast2") }
        args.append(contentsOf: tags.map { "-\($0)" })
        args.append(file)

        let raw = try execute(args)
        var result: [String: String] = [:]
        for line in raw.split(separator: "\n", omittingEmptySubsequences: false) {
            guard let colonIndex = line.firstIndex(of: ":") else { continue }
            let key = line[line.startIndex..<colonIndex].trimmingCharacters(in: .whitespaces)
            let value = line[line.index(after: colonIndex)...].trimmingCharacters(in: .whitespaces)
            if !key.isEmpty {
                result[key] = value
            }
        }
        return result
    }

    func writeTags(file: String, tags: [String: String]) throws -> (updated: Bool, filesChanged: Int) {
        var args = ["-P", "-overwrite_original"]
        for (key, value) in tags {
            args.append("-\(key)=\(value)")
        }
        args.append(file)

        let raw = try execute(args)
        let pattern = try NSRegularExpression(pattern: #"(\d+) image files? updated"#)
        let range = NSRange(raw.startIndex..., in: raw)
        if let match = pattern.firstMatch(in: raw, range: range),
           let numRange = Range(match.range(at: 1), in: raw),
           let count = Int(raw[numRange]) {
            return (true, count)
        }
        return (false, 0)
    }

    func close() {
        lock.lock()
        defer { lock.unlock() }

        guard let proc = process, proc.isRunning else {
            process = nil
            return
        }
        stdin?.write("-stay_open\nFalse\n".data(using: .utf8)!)
        proc.waitUntilExit()
        process = nil
    }

    deinit {
        close()
    }
}

enum MetadataError: Error {
    case notRunning
    case invalidRequest(String)
}

private extension CharacterSet {
    static let carriageReturns = CharacterSet(charactersIn: "\r")
}

let backend = ExifToolBackend()

func handleRequest(_ jsonLine: String) -> String {
    let decoder = JSONDecoder()
    guard let data = jsonLine.data(using: .utf8),
          let request = try? decoder.decode(Request.self, from: data) else {
        return #"{"error":"invalid JSON request"}"#
    }

    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]

    do {
        switch request.op {
        case "read":
            guard case .array(let tagList) = request.tags else {
                return #"{"error":"read requires tags as array"}"#
            }
            let result = try backend.readTags(
                file: request.file,
                tags: tagList,
                fast: request.fast ?? false
            )
            let responseData = try encoder.encode(result)
            return String(data: responseData, encoding: .utf8) ?? "{}"

        case "write":
            guard case .dictionary(let tagDict) = request.tags else {
                return #"{"error":"write requires tags as dictionary"}"#
            }
            let (updated, filesChanged) = try backend.writeTags(file: request.file, tags: tagDict)
            let response: [String: AnyCodableValue] = [
                "updated": .bool(updated),
                "files_changed": .int(filesChanged),
            ]
            let responseData = try encoder.encode(response)
            return String(data: responseData, encoding: .utf8) ?? "{}"

        default:
            return #"{"error":"unknown op: \#(request.op)"}"#
        }
    } catch {
        return #"{"error":"\#(error.localizedDescription)"}"#
    }
}

enum AnyCodableValue: Encodable {
    case bool(Bool)
    case int(Int)
    case string(String)

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .bool(let v): try container.encode(v)
        case .int(let v): try container.encode(v)
        case .string(let v): try container.encode(v)
        }
    }
}

while let line = readLine(strippingNewline: true) {
    let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
    if trimmed.isEmpty { continue }
    let response = handleRequest(trimmed)
    print(response)
    fflush(stdout)
}

backend.close()
