import Foundation

/// A script's output, handed over as everything that arrived while the consumer was
/// busy with the previous batch.
///
/// The app applies a run's output on the main actor, and every application redraws
/// the results table. One hop per line meant one redraw per line however far behind
/// the app was, so a long run's backlog grew faster than it drained and the app was
/// still drawing minutes after the pipeline had finished. Batched, a consumer that
/// falls behind catches up in one hop.
final class ArrivalBatches<Item>: AsyncSequence, @unchecked Sendable {
    typealias Element = [Item]

    private let lock = NSLock()
    private var pending: [Item] = []
    private var finished = false
    private var waiting: CheckedContinuation<[Item]?, Never>?
    private var reader: Task<Void, Never>?

    init() {}

    convenience init(_ stream: AsyncStream<Item>) {
        self.init()
        reader = Task { [self] in
            for await item in stream {
                receive(item)
            }
            finish()
        }
    }

    func receive(_ item: Item) {
        let handOff: (CheckedContinuation<[Item]?, Never>, [Item])? = lock.withLock {
            pending.append(item)
            guard let waiting else { return nil }
            self.waiting = nil
            defer { pending = [] }
            return (waiting, pending)
        }
        if let (consumer, batch) = handOff {
            consumer.resume(returning: batch)
        }
    }

    func finish() {
        let consumer: CheckedContinuation<[Item]?, Never>? = lock.withLock {
            finished = true
            defer { waiting = nil }
            return waiting
        }
        consumer?.resume(returning: nil)
    }

    private func nextBatch() async -> [Item]? {
        await withTaskCancellationHandler {
            await withCheckedContinuation { (consumer: CheckedContinuation<[Item]?, Never>) in
                let ready: [Item]?? = lock.withLock {
                    if !pending.isEmpty {
                        defer { pending = [] }
                        return .some(pending)
                    }
                    if finished { return .some(nil) }
                    waiting = consumer
                    return .none
                }
                if let ready {
                    consumer.resume(returning: ready)
                }
            }
        } onCancel: {
            reader?.cancel()
            finish()
        }
    }

    struct AsyncIterator: AsyncIteratorProtocol {
        let batches: ArrivalBatches

        mutating func next() async -> [Item]? {
            await batches.nextBatch()
        }
    }

    func makeAsyncIterator() -> AsyncIterator {
        AsyncIterator(batches: self)
    }
}
