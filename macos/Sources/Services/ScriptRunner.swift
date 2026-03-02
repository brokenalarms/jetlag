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
        let toolsDir = (workingDir as NSString).appendingPathComponent("tools")
        let existingPath = env["PATH"] ?? "/usr/bin:/bin"
        env["PATH"] = toolsDir + ":" + existingPath
        process.environment = env

        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        let stream = AsyncStream<LogLine> { continuation in
            let group = DispatchGroup()

            func readLines(from pipe: Pipe, stream: LogLine.Stream) {
                group.enter()
                // Buffer for partial lines that span pipe chunk boundaries.
                // Without this, a chunk ending mid-line (e.g. '{"event":"timestamp_res')
                // would be yielded as an incomplete line and the remainder lost.
                var partialLine = ""
                pipe.fileHandleForReading.readabilityHandler = { handle in
                    let data = handle.availableData
                    guard !data.isEmpty else {
                        if !partialLine.isEmpty {
                            continuation.yield(LogLine(text: partialLine, stream: stream))
                            partialLine = ""
                        }
                        pipe.fileHandleForReading.readabilityHandler = nil
                        group.leave()
                        return
                    }
                    if let text = String(data: data, encoding: .utf8) {
                        let combined = partialLine + text
                        partialLine = ""
                        let segments = combined.components(separatedBy: .newlines)
                        for (i, segment) in segments.enumerated() {
                            if i == segments.count - 1 {
                                // Last segment may be a partial line (no trailing newline)
                                partialLine = segment
                            } else if !segment.isEmpty {
                                continuation.yield(LogLine(text: segment, stream: stream))
                            }
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
                continuation.yield(LogLine(text: Strings.Errors.scriptStartFailed(error.localizedDescription), stream: .stderr))
                continuation.finish()
            }
        }

        return (process, stream)
    }
}
