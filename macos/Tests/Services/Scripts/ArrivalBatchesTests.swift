import XCTest
@testable import Jetlag

/// A run's output is applied on the main actor, and each application redraws the
/// table. Lines that arrive while the consumer is busy must come to it together, so a
/// consumer that falls behind catches up in one step instead of one step per line.
final class ArrivalBatchesTests: XCTestCase {

    func testEverythingThatArrivedWhileTheConsumerWasBusyIsOneBatch() async {
        let batches = ArrivalBatches<Int>()
        var iterator = batches.makeAsyncIterator()
        for i in 1...50 { batches.receive(i) }

        let first = await iterator.next()
        XCTAssertEqual(first, Array(1...50))

        batches.receive(51)
        batches.finish()
        let second = await iterator.next()
        let end = await iterator.next()
        XCTAssertEqual(second, [51])
        XCTAssertNil(end)
    }

    func testAWaitingConsumerIsHandedTheNextArrival() async {
        let batches = ArrivalBatches<Int>()
        let waiting = Task {
            var iterator = batches.makeAsyncIterator()
            return await iterator.next()
        }
        batches.receive(7)
        let batch = await waiting.value
        XCTAssertEqual(batch, [7])
    }

    func testCancellingAWaitingConsumerEndsItsBatches() async {
        let batches = ArrivalBatches<Int>()
        let waiting = Task {
            var iterator = batches.makeAsyncIterator()
            return await iterator.next()
        }
        waiting.cancel()
        let batch = await waiting.value
        XCTAssertNil(batch)
    }

    /// Batching a stream delivers every element once, in order, and ends with it.
    func testABatchedStreamDeliversEveryElementInOrder() async {
        let (stream, continuation) = AsyncStream<Int>.makeStream()
        for i in 1...200 { continuation.yield(i) }
        continuation.finish()

        var delivered: [Int] = []
        for await batch in ArrivalBatches(stream) {
            delivered += batch
        }
        XCTAssertEqual(delivered, Array(1...200))
    }
}
