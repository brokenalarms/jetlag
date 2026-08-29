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
    /// exiftool's pid, 0 when it is not running. Bookkeeping is pid-based rather
    /// than `Process`-based because `Process` puts the child in a process group of
    /// its own: the app cancels a run by signalling the pipeline's group, so an
    /// exiftool outside that group is never reached and outlives the run.
    private var pid: pid_t = 0
    private var stdinFD: Int32 = -1
    private var stdoutFD: Int32 = -1
    private var stderrHandle: FileHandle?
    private var execId = 0
    private let lock = NSLock()

    private let exited = NSCondition()
    private var hasExited = true

    /// exiftool's stderr, drained continuously off the main thread. A pipe nobody
    /// reads fills after ~16 KB; exiftool then blocks on its next warning before it
    /// prints `{ready}`, and every layer above waits forever. Every `.insv` write
    /// emits an "Insta360 trailer" warning, so a real card reached that after a few
    /// hundred files. Only the tail is kept; each request takes what accumulated.
    private let stderrLock = NSLock()
    private var stderrBuffer = Data()
    private static let stderrKeep = 64 * 1024

    /// How long exiftool is given to exit after `-stay_open False` before it is killed.
    private static let shutdownGracePeriod: TimeInterval = 5

    var isRunning: Bool {
        exited.lock()
        defer { exited.unlock() }
        return pid > 0 && !hasExited
    }

    func ensureRunning() throws {
        if isRunning { return }

        let exiftoolPath = resolveExifToolPath()
        let arguments = [exiftoolPath, "-stay_open", "True", "-@", "-"]

        var toChild: [Int32] = [-1, -1]
        var fromChild: [Int32] = [-1, -1]
        var childErrors: [Int32] = [-1, -1]
        guard pipe(&toChild) == 0, pipe(&fromChild) == 0, pipe(&childErrors) == 0 else {
            throw MetadataError.spawnFailed(String(cString: strerror(errno)))
        }

        var fileActions: posix_spawn_file_actions_t?
        posix_spawn_file_actions_init(&fileActions)
        defer { posix_spawn_file_actions_destroy(&fileActions) }
        posix_spawn_file_actions_adddup2(&fileActions, toChild[0], STDIN_FILENO)
        posix_spawn_file_actions_adddup2(&fileActions, fromChild[1], STDOUT_FILENO)
        posix_spawn_file_actions_adddup2(&fileActions, childErrors[1], STDERR_FILENO)

        var attributes: posix_spawnattr_t?
        posix_spawnattr_init(&attributes)
        defer { posix_spawnattr_destroy(&attributes) }
        // No SETPGROUP: exiftool stays in this process's group, so the group signal
        // the app's Cancel sends reaches it directly. SETSIGDEF undoes the SIG_IGN
        // this process installs to observe SIGINT and SIGTERM — inherited, it would
        // make exiftool ignore the very signal that is meant to stop it — and
        // CLOEXEC_DEFAULT hands the child only the three descriptors dup2'd above.
        var defaultedSignals = sigset_t()
        sigfillset(&defaultedSignals)
        posix_spawnattr_setsigdefault(&attributes, &defaultedSignals)
        var unblockedSignals = sigset_t()
        sigemptyset(&unblockedSignals)
        posix_spawnattr_setsigmask(&attributes, &unblockedSignals)
        posix_spawnattr_setflags(
            &attributes,
            Int16(POSIX_SPAWN_CLOEXEC_DEFAULT | POSIX_SPAWN_SETSIGDEF | POSIX_SPAWN_SETSIGMASK))

        var spawnedPid: pid_t = 0
        let result = withCStringArray(arguments) { argv in
            posix_spawnp(&spawnedPid, exiftoolPath, &fileActions, &attributes, argv, environ)
        }

        Darwin.close(toChild[0])
        Darwin.close(fromChild[1])
        Darwin.close(childErrors[1])
        guard result == 0 else {
            Darwin.close(toChild[1])
            Darwin.close(fromChild[0])
            Darwin.close(childErrors[0])
            throw MetadataError.spawnFailed(String(cString: strerror(result)))
        }

        stdinFD = toChild[1]
        stdoutFD = fromChild[0]
        drainStandardError(from: childErrors[0])

        pid = spawnedPid
        hasExited = false
        // Reaped on a thread of its own: nothing else waits on exiftool, and an
        // unreaped child would linger as a zombie for the life of the run.
        Thread.detachNewThread { [self] in
            var status: Int32 = 0
            while waitpid(spawnedPid, &status, 0) < 0 && errno == EINTR {}
            exited.lock()
            hasExited = true
            exited.broadcast()
            exited.unlock()
        }
    }

    private func drainStandardError(from descriptor: Int32) {
        let handle = FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
        handle.readabilityHandler = { [weak self] handle in
            let chunk = handle.availableData
            guard let self else { return }
            if chunk.isEmpty {
                handle.readabilityHandler = nil
                return
            }
            self.stderrLock.lock()
            self.stderrBuffer.append(chunk)
            if self.stderrBuffer.count > Self.stderrKeep {
                self.stderrBuffer.removeFirst(self.stderrBuffer.count - Self.stderrKeep)
            }
            self.stderrLock.unlock()
        }
        stderrHandle = handle
    }

    /// Call `body` with a NULL-terminated `char *[]` view of `values`, valid only
    /// for the duration of the call.
    private func withCStringArray<R>(
        _ values: [String],
        _ body: (UnsafePointer<UnsafeMutablePointer<CChar>?>) -> R
    ) -> R {
        var pointers = values.map { strdup($0) }
        pointers.append(nil)
        defer { pointers.forEach { free($0) } }
        return body(&pointers)
    }

    /// What exiftool wrote to stderr since the last call — warnings for the request
    /// just completed, surfaced to the caller instead of left in the pipe.
    func takeWarnings() -> String {
        stderrLock.lock()
        defer { stderrLock.unlock() }
        let text = String(data: stderrBuffer, encoding: .utf8) ?? ""
        stderrBuffer.removeAll(keepingCapacity: true)
        return text.trimmingCharacters(in: .whitespacesAndNewlines)
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
        guard stdinFD >= 0, stdoutFD >= 0 else {
            throw MetadataError.notRunning
        }

        execId += 1
        let sentinel = "{ready\(execId)}"

        let payload = args.joined(separator: "\n") + "\n-execute\(execId)\n"
        guard writeToExifTool(payload) else {
            throw MetadataError.notRunning
        }

        var lines: [String] = []
        var buffer = Data()

        while true {
            let chunk = readFromExifTool()
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

    /// Shut exiftool down and release its descriptors.
    ///
    /// Called from a signal handler as well as from the end of the main loop, so
    /// it takes the lock opportunistically: the signalled thread may already hold
    /// it inside `execute`, and blocking here would leave exiftool running. An
    /// exiftool the same signal has already killed is a success, not an error —
    /// the write simply fails, and the wait finds a process that is already gone.
    func close() {
        let acquired = lock.try()
        defer { if acquired { lock.unlock() } }

        if pid > 0 {
            if isRunning {
                _ = writeToExifTool("-stay_open\nFalse\n")
                if !waitForExit(within: Self.shutdownGracePeriod) {
                    kill(pid, SIGKILL)
                    _ = waitForExit(within: Self.shutdownGracePeriod)
                }
            }
            pid = 0
        }

        stderrHandle?.readabilityHandler = nil
        stderrHandle = nil
        if stdinFD >= 0 { Darwin.close(stdinFD) }
        if stdoutFD >= 0 { Darwin.close(stdoutFD) }
        stdinFD = -1
        stdoutFD = -1
    }

    /// Write to exiftool, reporting whether it took the bytes. SIGPIPE is ignored
    /// process-wide, so a write to an exiftool that has already exited returns
    /// EPIPE here instead of killing this process.
    private func writeToExifTool(_ text: String) -> Bool {
        guard stdinFD >= 0 else { return false }
        let bytes = Array(text.utf8)
        var offset = 0
        while offset < bytes.count {
            let written = bytes[offset...].withUnsafeBufferPointer { buffer in
                write(stdinFD, buffer.baseAddress, buffer.count)
            }
            if written < 0 {
                if errno == EINTR { continue }
                return false
            }
            offset += written
        }
        return true
    }

    private func readFromExifTool() -> Data {
        guard stdoutFD >= 0 else { return Data() }
        var buffer = [UInt8](repeating: 0, count: 8192)
        while true {
            let count = buffer.withUnsafeMutableBufferPointer { pointer in
                read(stdoutFD, pointer.baseAddress, pointer.count)
            }
            if count < 0 {
                if errno == EINTR { continue }
                return Data()
            }
            return Data(buffer[0..<count])
        }
    }

    private func waitForExit(within timeout: TimeInterval) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        exited.lock()
        defer { exited.unlock() }
        while !hasExited, Date() < deadline {
            exited.wait(until: deadline)
        }
        return hasExited
    }

    deinit {
        close()
    }
}

enum MetadataError: Error {
    case notRunning
    case spawnFailed(String)
    case invalidRequest(String)
}

private extension CharacterSet {
    static let carriageReturns = CharacterSet(charactersIn: "\r")
}

let backend = ExifToolBackend()

/// Shut exiftool down on the signals the app's Cancel sends, then exit with the
/// status a signalled process reports.
///
/// The app cancels a run by signalling the pipeline's process group, so this
/// process and its exiftool are signalled at the same instant. Without a handler
/// this process dies immediately and exiftool — mid-command, holding its
/// stay_open state — is left to be reaped by whatever comes next. SIGPIPE is
/// ignored so that writing `-stay_open False` to an exiftool the same signal has
/// already killed fails a write instead of killing the shutdown that is running.
func installShutdownHandlers() -> [DispatchSourceSignal] {
    signal(SIGPIPE, SIG_IGN)
    return [SIGINT, SIGTERM].map { signalNumber in
        // The default disposition has to go before the source can observe it:
        // otherwise the process is dead before the handler is ever scheduled.
        signal(signalNumber, SIG_IGN)
        let source = DispatchSource.makeSignalSource(signal: signalNumber, queue: .global())
        source.setEventHandler {
            backend.close()
            exit(128 + signalNumber)
        }
        source.resume()
        return source
    }
}

let shutdownHandlers = installShutdownHandlers()

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
            var result = try backend.readTags(
                file: request.file,
                tags: tagList,
                fast: request.fast ?? false
            )
            let warnings = backend.takeWarnings()
            if !warnings.isEmpty { result["_warnings"] = warnings }
            let responseData = try encoder.encode(result)
            return String(data: responseData, encoding: .utf8) ?? "{}"

        case "write":
            guard case .dictionary(let tagDict) = request.tags else {
                return #"{"error":"write requires tags as dictionary"}"#
            }
            let (updated, filesChanged) = try backend.writeTags(file: request.file, tags: tagDict)
            var response: [String: AnyCodableValue] = [
                "updated": .bool(updated),
                "files_changed": .int(filesChanged),
            ]
            let warnings = backend.takeWarnings()
            if !warnings.isEmpty { response["warnings"] = .string(warnings) }
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
