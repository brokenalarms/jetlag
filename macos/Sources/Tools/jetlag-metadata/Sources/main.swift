import Foundation

@MainActor
final class ExifToolProcess {
    private let process: Process
    private let stdinPipe: Pipe
    private let stdoutPipe: Pipe
    private var execID = 0

    init(exiftoolPath: String) throws {
        process = Process()
        process.executableURL = URL(fileURLWithPath: exiftoolPath)
        process.arguments = ["-stay_open", "True", "-@", "-"]

        stdinPipe = Pipe()
        stdoutPipe = Pipe()
        process.standardInput = stdinPipe
        process.standardOutput = stdoutPipe
        process.standardError = Pipe()

        try process.run()
    }

    func execute(_ args: [String]) -> String {
        execID += 1
        let sentinel = "{ready\(execID)}"

        let payload = args.joined(separator: "\n") + "\n-execute\(execID)\n"
        stdinPipe.fileHandleForWriting.write(payload.data(using: .utf8)!)

        var lines: [String] = []
        let handle = stdoutPipe.fileHandleForReading
        var buffer = Data()

        while true {
            let chunk = handle.availableData
            if chunk.isEmpty { break }
            buffer.append(chunk)

            while let newlineRange = buffer.range(of: Data([0x0A])) {
                let lineData = buffer[buffer.startIndex..<newlineRange.lowerBound]
                let line = String(data: lineData, encoding: .utf8)?
                    .trimmingCharacters(in: .carriageReturns) ?? ""
                buffer.removeSubrange(buffer.startIndex...newlineRange.lowerBound)

                if line == sentinel {
                    return lines.joined(separator: "\n")
                }
                lines.append(line)
            }
        }
        return lines.joined(separator: "\n")
    }

    func shutdown() {
        stdinPipe.fileHandleForWriting.write("-stay_open\nFalse\n".data(using: .utf8)!)
        process.waitUntilExit()
    }
}

private extension CharacterSet {
    static let carriageReturns = CharacterSet(charactersIn: "\r")
}

@MainActor
struct MetadataService {
    private let exiftool: ExifToolProcess

    init(exiftool: ExifToolProcess) {
        self.exiftool = exiftool
    }

    func readTags(file: String, tags: [String], fast: Bool) -> [String: String] {
        var args = ["-s"]
        if fast { args.append("-fast2") }
        args += tags.map { "-\($0)" }
        args.append(file)

        let output = exiftool.execute(args)
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

        let output = exiftool.execute(args)
        let pattern = /(\d+) image files? updated/
        if let match = output.firstMatch(of: pattern),
           let count = Int(match.1), count > 0 {
            return (true, count)
        }
        return (false, 0)
    }
}

func findExifTool() -> String {
    let bundleDir = URL(fileURLWithPath: CommandLine.arguments[0])
        .deletingLastPathComponent().path
    let vendored = (bundleDir as NSString).appendingPathComponent("exiftool")
    if FileManager.default.isExecutableFile(atPath: vendored) {
        return vendored
    }
    if let pathEnv = ProcessInfo.processInfo.environment["PATH"] {
        for dir in pathEnv.split(separator: ":") {
            let candidate = "\(dir)/exiftool"
            if FileManager.default.isExecutableFile(atPath: candidate) {
                return candidate
            }
        }
    }
    return "exiftool"
}

func emitJSON(_ value: Any) {
    if let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]) {
        print(String(data: data, encoding: .utf8) ?? "{}")
    } else {
        print("{}")
    }
    fflush(stdout)
}

@MainActor
func main() {
    let exiftoolProcess: ExifToolProcess
    do {
        exiftoolProcess = try ExifToolProcess(exiftoolPath: findExifTool())
    } catch {
        FileHandle.standardError.write("failed to start exiftool: \(error)\n".data(using: .utf8)!)
        exit(1)
    }

    let service = MetadataService(exiftool: exiftoolProcess)

    while let line = readLine() {
        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { continue }

        guard let data = trimmed.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let op = json["op"] as? String,
              let file = json["file"] as? String
        else {
            emitJSON([:] as [String: String])
            continue
        }

        switch op {
        case "read":
            guard let tags = json["tags"] as? [String] else {
                emitJSON([:] as [String: String])
                continue
            }
            let fast = json["fast"] as? Bool ?? false
            emitJSON(service.readTags(file: file, tags: tags, fast: fast))

        case "write":
            guard let tags = json["tags"] as? [String: String] else {
                emitJSON([:] as [String: String])
                continue
            }
            let (updated, filesChanged) = service.writeTags(file: file, tags: tags)
            emitJSON(["updated": updated, "files_changed": filesChanged] as [String: Any])

        default:
            emitJSON([:] as [String: String])
        }
    }

    exiftoolProcess.shutdown()
}

main()
