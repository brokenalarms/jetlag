import Foundation

final class ExifToolProcess {
    private var process: Process?
    private var stdin: FileHandle?
    private var stdout: FileHandle?
    private var execID = 0

    func ensureRunning() throws {
        if let p = process, p.isRunning { return }

        let p = Process()
        p.executableURL = exiftoolURL()
        p.arguments = ["-stay_open", "True", "-@", "-"]

        let stdinPipe = Pipe()
        let stdoutPipe = Pipe()
        p.standardInput = stdinPipe
        p.standardOutput = stdoutPipe
        p.standardError = FileHandle.nullDevice

        try p.run()

        self.process = p
        self.stdin = stdinPipe.fileHandleForWriting
        self.stdout = stdoutPipe.fileHandleForReading
    }

    func execute(_ args: [String]) throws -> String {
        try ensureRunning()
        guard let stdin = stdin, let stdout = stdout else {
            throw MetadataError.processNotRunning
        }

        execID += 1
        let sentinel = "{ready\(execID)}"

        var payload = args.joined(separator: "\n")
        payload += "\n-execute\(execID)\n"

        stdin.write(Data(payload.utf8))

        var lines: [String] = []
        var buffer = Data()

        while true {
            let chunk = stdout.availableData
            if chunk.isEmpty { break }
            buffer.append(chunk)

            while let newlineRange = buffer.range(of: Data([0x0A])) {
                let lineData = buffer[buffer.startIndex..<newlineRange.lowerBound]
                let line = String(data: lineData, encoding: .utf8) ?? ""
                buffer.removeSubrange(buffer.startIndex...newlineRange.lowerBound)

                let trimmed = line.trimmingCharacters(in: .carriageReturns)
                if trimmed == sentinel {
                    return lines.joined(separator: "\n")
                }
                lines.append(trimmed)
            }
        }

        return lines.joined(separator: "\n")
    }

    func readTags(file: String, tags: [String], fast: Bool) throws -> [String: String] {
        var args = ["-s"]
        if fast {
            args.append("-fast2")
        }
        args.append(contentsOf: tags.map { "-\($0)" })
        args.append(file)

        let raw = try execute(args)
        var result: [String: String] = [:]

        for line in raw.split(separator: "\n", omittingEmptySubsequences: true) {
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

        let output = try execute(args)

        if let range = output.range(of: #"(\d+) image files? updated"#, options: .regularExpression) {
            let match = output[range]
            if let numRange = match.range(of: #"\d+"#, options: .regularExpression) {
                let count = Int(match[numRange]) ?? 0
                return (count > 0, count)
            }
        }
        return (false, 0)
    }

    func shutdown() {
        guard let p = process, p.isRunning else { return }
        stdin?.write(Data("-stay_open\nFalse\n".utf8))
        p.waitUntilExit()
        process = nil
        stdin = nil
        stdout = nil
    }

    private func exiftoolURL() -> URL {
        if let bundled = Bundle.main.url(forAuxiliaryExecutable: "exiftool") {
            return bundled
        }

        let adjacent = URL(fileURLWithPath: CommandLine.arguments[0])
            .deletingLastPathComponent()
            .appendingPathComponent("exiftool")
        if FileManager.default.isExecutableFile(atPath: adjacent.path) {
            return adjacent
        }

        return URL(fileURLWithPath: "/usr/local/bin/exiftool")
    }
}

private extension CharacterSet {
    static let carriageReturns = CharacterSet(charactersIn: "\r")
}
