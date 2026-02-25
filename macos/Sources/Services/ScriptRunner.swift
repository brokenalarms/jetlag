import Foundation

struct ScriptRunner {
    static func run(
        script: String,
        args: [String],
        workingDir: String
    ) -> (process: Process, stream: AsyncStream<LogLine>) {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/bash")
        process.arguments = [
            (workingDir as NSString).appendingPathComponent(script)
        ] + args
        process.currentDirectoryURL = URL(fileURLWithPath: workingDir)

        var env = ProcessInfo.processInfo.environment
        env["PATH"] = ScriptRunner.loginPath()
        process.environment = env

        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        let stream = AsyncStream<LogLine> { continuation in
            let group = DispatchGroup()

            func readLines(from pipe: Pipe, stream: LogLine.Stream) {
                group.enter()
                pipe.fileHandleForReading.readabilityHandler = { handle in
                    let data = handle.availableData
                    guard !data.isEmpty else {
                        pipe.fileHandleForReading.readabilityHandler = nil
                        group.leave()
                        return
                    }
                    if let text = String(data: data, encoding: .utf8) {
                        for line in text.components(separatedBy: .newlines) where !line.isEmpty {
                            continuation.yield(LogLine(text: line, stream: stream))
                        }
                    }
                }
            }

            readLines(from: stdoutPipe, stream: .stdout)
            readLines(from: stderrPipe, stream: .stderr)

            group.notify(queue: .global()) {
                continuation.finish()
            }

            do {
                try process.run()
            } catch {
                stdoutPipe.fileHandleForReading.readabilityHandler = nil
                stderrPipe.fileHandleForReading.readabilityHandler = nil
                continuation.yield(LogLine(text: "Failed to start: \(error.localizedDescription)", stream: .stderr))
                continuation.finish()
            }
        }

        return (process, stream)
    }

    static func loginPath() -> String {
        var paths = ["/opt/homebrew/bin", "/usr/local/bin"]

        if let etcPaths = try? String(contentsOfFile: "/etc/paths", encoding: .utf8) {
            paths += etcPaths.components(separatedBy: .newlines).filter { !$0.isEmpty }
        }

        let pathsD = (try? FileManager.default.contentsOfDirectory(atPath: "/etc/paths.d")) ?? []
        for file in pathsD {
            if let content = try? String(contentsOfFile: "/etc/paths.d/\(file)", encoding: .utf8) {
                paths += content.components(separatedBy: .newlines).filter { !$0.isEmpty }
            }
        }

        let current = ProcessInfo.processInfo.environment["PATH"] ?? ""
        if !current.isEmpty {
            paths += current.components(separatedBy: ":")
        }

        var seen = Set<String>()
        return paths.filter { seen.insert($0).inserted }.joined(separator: ":")
    }
}
