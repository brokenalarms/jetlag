import Foundation

/// Turns one end of a pipe into complete log lines.
///
/// Reading is driven by a read source on a serial queue, so the ordinary
/// EOF-driven finish and the finish forced once the script has exited cannot
/// interleave — both run on that queue, and whichever gets there first wins.
final class PipeLineReader: @unchecked Sendable {
    private let handle: FileHandle
    private let stream: LogLine.Stream
    private let emit: (LogLine) -> Void
    private let onFinished: () -> Void
    private let queue: DispatchQueue
    private let source: DispatchSourceRead
    /// Buffer for a partial line that spans pipe chunk boundaries. Without it a
    /// chunk ending mid-line (e.g. `{"event":"timestamp_res`) would be emitted as
    /// an incomplete line and the remainder lost.
    private var partialLine = ""
    private var isFinished = false

    private static let readChunkSize = 64 * 1024

    init(
        handle: FileHandle,
        stream: LogLine.Stream,
        emit: @escaping (LogLine) -> Void,
        onFinished: @escaping () -> Void
    ) {
        self.handle = handle
        self.stream = stream
        self.emit = emit
        self.onFinished = onFinished
        queue = DispatchQueue(label: "com.daniellawrence.Jetlag.pipe-reader")
        // Non-blocking, so a read that finds the pipe empty returns instead of
        // parking the queue until the next write — which for a pipe still held
        // open by a lingering descendant might never come.
        let descriptor = handle.fileDescriptor
        _ = fcntl(descriptor, F_SETFL, fcntl(descriptor, F_GETFL) | O_NONBLOCK)
        source = DispatchSource.makeReadSource(fileDescriptor: descriptor, queue: queue)
        source.setEventHandler { [weak self] in
            self?.readAvailable()
        }
        source.setCancelHandler { [handle] in
            try? handle.close()
        }
        source.resume()
    }

    /// Stop reading once the script has exited, keeping whatever it wrote before
    /// it did. A descendant may still hold the write end open, so this drains the
    /// bytes already in the pipe rather than waiting for an EOF that is not coming.
    func finishDrainingBufferedOutput() {
        queue.async { [self] in
            guard !isFinished else { return }
            drainAvailableData()
            finish()
        }
    }

    private func readAvailable() {
        guard !isFinished else { return }
        if drainAvailableData() == .endOfFile {
            finish()
        }
    }

    private enum DrainOutcome {
        case exhausted
        case endOfFile
    }

    /// Read everything currently buffered in the pipe. Returns as soon as the
    /// pipe is empty — the read source, not a loop, is what waits for more.
    @discardableResult
    private func drainAvailableData() -> DrainOutcome {
        var buffer = [UInt8](repeating: 0, count: Self.readChunkSize)
        while true {
            let count = buffer.withUnsafeMutableBytes {
                read(handle.fileDescriptor, $0.baseAddress, Self.readChunkSize)
            }
            if count > 0 {
                consume(Data(buffer[0..<count]))
            } else if count == 0 {
                return .endOfFile
            } else if errno == EINTR {
                continue
            } else if errno == EAGAIN || errno == EWOULDBLOCK {
                return .exhausted
            } else {
                return .endOfFile
            }
        }
    }

    private func consume(_ data: Data) {
        guard let text = String(data: data, encoding: .utf8) else { return }
        let segments = (partialLine + text).components(separatedBy: .newlines)
        partialLine = ""
        for (index, segment) in segments.enumerated() {
            if index == segments.count - 1 {
                // The last segment has no newline after it yet.
                partialLine = segment
            } else if !segment.isEmpty {
                emit(LogLine(text: segment, stream: stream))
            }
        }
    }

    private func finish() {
        isFinished = true
        if !partialLine.isEmpty {
            emit(LogLine(text: partialLine, stream: stream))
            partialLine = ""
        }
        source.cancel()
        onFinished()
    }
}
