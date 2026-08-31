import Foundation

struct ScriptRunner {
    static func run(
        script: String,
        args: [String],
        workingDir: String,
        profilesPath: String
    ) -> (process: ScriptProcess, stream: AsyncStream<LogLine>) {
        let arguments = [
            "/bin/bash",
            (workingDir as NSString).appendingPathComponent(script),
        ] + args

        var env = ProcessInfo.processInfo.environment
        let toolsDir = (workingDir as NSString).appendingPathComponent("tools")
        let existingPath = env["PATH"] ?? "/usr/bin:/bin"
        env["PATH"] = toolsDir + ":" + existingPath
        // Without this the scripts fall back to <scripts>/media-profiles.yaml —
        // the read-only copy in the bundle, not the file the app writes.
        env[ProfilesLocation.environmentKey] = profilesPath

        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()

        var spawned: ScriptProcess?
        let stream = AsyncStream<LogLine> { continuation in
            let group = DispatchGroup()

            func reader(for pipe: Pipe, stream: LogLine.Stream) -> PipeLineReader {
                group.enter()
                return PipeLineReader(
                    handle: pipe.fileHandleForReading,
                    stream: stream,
                    emit: { continuation.yield($0) },
                    onFinished: { group.leave() }
                )
            }

            let stdoutReader = reader(for: stdoutPipe, stream: .stdout)
            let stderrReader = reader(for: stderrPipe, stream: .stderr)

            group.notify(queue: .global()) {
                continuation.finish()
            }

            do {
                let process = try spawnProcessGroupLeader(
                    arguments: arguments,
                    environment: env,
                    workingDir: workingDir,
                    stdout: stdoutPipe.fileHandleForWriting,
                    stderr: stderrPipe.fileHandleForWriting
                )
                spawned = process
                // The run ends when the script ends, not when the pipes reach EOF.
                // The script's stdout and stderr are fd 1 and 2 in every descendant
                // it spawns, so one that outlives it — a wedged exiftool, a gyroflow
                // left running — holds the write ends open and EOF never arrives.
                // Waiting on the leader instead is an event, not a poll: waitpid
                // returns, the buffered output is drained, and the readers finish,
                // so the stream ends and the app's completion handling runs.
                Thread.detachNewThread {
                    process.waitUntilExit()
                    stdoutReader.finishDrainingBufferedOutput()
                    stderrReader.finishDrainingBufferedOutput()
                }
            } catch {
                continuation.yield(LogLine(text: Strings.Errors.scriptStartFailed(error.localizedDescription), stream: .stderr))
            }
            // The child owns the write ends now; holding them open here would keep
            // the reads from ever seeing EOF, so a run whose descendants all exit —
            // and a spawn that failed outright — would never finish.
            try? stdoutPipe.fileHandleForWriting.close()
            try? stderrPipe.fileHandleForWriting.close()
        }

        return (spawned ?? ScriptProcess(processIdentifier: -1), stream)
    }

    /// Spawn the script as the leader of a fresh process group.
    ///
    /// `Process` offers no way to do this, and it is what makes cancel able to
    /// reach the pipeline's descendants — jetlag-metadata and the persistent
    /// exiftool it owns — instead of only the script itself.
    private static func spawnProcessGroupLeader(
        arguments: [String],
        environment: [String: String],
        workingDir: String,
        stdout: FileHandle,
        stderr: FileHandle
    ) throws -> ScriptProcess {
        var fileActions: posix_spawn_file_actions_t?
        posix_spawn_file_actions_init(&fileActions)
        defer { posix_spawn_file_actions_destroy(&fileActions) }
        posix_spawn_file_actions_addopen(&fileActions, STDIN_FILENO, "/dev/null", O_RDONLY, 0)
        posix_spawn_file_actions_adddup2(&fileActions, stdout.fileDescriptor, STDOUT_FILENO)
        posix_spawn_file_actions_adddup2(&fileActions, stderr.fileDescriptor, STDERR_FILENO)
        posix_spawn_file_actions_addchdir_np(&fileActions, workingDir)

        var attributes: posix_spawnattr_t?
        posix_spawnattr_init(&attributes)
        defer { posix_spawnattr_destroy(&attributes) }
        // pgroup 0 means "a new group led by the child". CLOEXEC_DEFAULT drops every
        // descriptor except the three set up above: the child would otherwise also
        // inherit the pipes' write ends by their original numbers, and anything it
        // backgrounds would hold them open long past its own exit, keeping the
        // pipes alive well after the run has ended. SETSIGDEF and SETSIGMASK hand
        // the script a clean signal environment: an inherited SIG_IGN cannot be
        // trapped and an inherited block leaves the signal pending forever, so a
        // script launched from a host that ignores or blocks SIGINT — as a Swift
        // runtime does — would ignore cancel outright.
        var defaultedSignals = sigset_t()
        sigfillset(&defaultedSignals)
        posix_spawnattr_setsigdefault(&attributes, &defaultedSignals)
        var unblockedSignals = sigset_t()
        sigemptyset(&unblockedSignals)
        posix_spawnattr_setsigmask(&attributes, &unblockedSignals)
        posix_spawnattr_setpgroup(&attributes, 0)
        posix_spawnattr_setflags(
            &attributes,
            Int16(POSIX_SPAWN_SETPGROUP | POSIX_SPAWN_CLOEXEC_DEFAULT
                  | POSIX_SPAWN_SETSIGDEF | POSIX_SPAWN_SETSIGMASK))

        let envStrings = environment.map { "\($0.key)=\($0.value)" }
        var pid: pid_t = 0
        let result = withCStringArray(arguments) { argv in
            withCStringArray(envStrings) { envp in
                posix_spawn(&pid, arguments[0], &fileActions, &attributes, argv, envp)
            }
        }
        guard result == 0 else {
            throw NSError(domain: NSPOSIXErrorDomain, code: Int(result), userInfo: [
                NSLocalizedDescriptionKey: String(cString: strerror(result)),
            ])
        }
        return ScriptProcess(processIdentifier: pid)
    }

    /// Call `body` with a NULL-terminated `char *[]` view of `values`, valid only
    /// for the duration of the call.
    private static func withCStringArray<R>(
        _ values: [String],
        _ body: (UnsafePointer<UnsafeMutablePointer<CChar>?>) -> R
    ) -> R {
        var pointers = values.map { strdup($0) }
        pointers.append(nil)
        defer { pointers.forEach { free($0) } }
        return body(&pointers)
    }
}
