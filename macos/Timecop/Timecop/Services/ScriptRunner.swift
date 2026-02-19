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

        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        let stream = AsyncStream<LogLine> { continuation in
            func readLines(from pipe: Pipe, stream: LogLine.Stream) {
                pipe.fileHandleForReading.readabilityHandler = { handle in
                    let data = handle.availableData
                    guard !data.isEmpty else {
                        pipe.fileHandleForReading.readabilityHandler = nil
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

            process.terminationHandler = { _ in
                continuation.finish()
            }

            do {
                try process.run()
            } catch {
                continuation.yield(LogLine(text: "Failed to start: \(error.localizedDescription)", stream: .stderr))
                continuation.finish()
            }
        }

        return (process, stream)
    }
}
