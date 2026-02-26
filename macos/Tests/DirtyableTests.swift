import XCTest
@testable import Jetlag

final class DirtyableTests: XCTestCase {

    // MARK: - String (Equatable)

    func testInitiallyNotDirty() {
        let field = Dirtyable("hello")
        XCTAssertFalse(field.isDirty)
        XCTAssertEqual(field.current, "hello")
    }

    func testMutationMarksDirty() {
        var field = Dirtyable("hello")
        field.value = "world"
        XCTAssertTrue(field.isDirty)
        XCTAssertEqual(field.current, "world")
    }

    func testEquatableRevertClearsDirty() {
        var field = Dirtyable("hello")
        field.value = "world"
        XCTAssertTrue(field.isDirty)
        field.value = "hello"
        XCTAssertFalse(field.isDirty)
    }

    func testCommitAcceptsChanges() {
        var field = Dirtyable("hello")
        field.value = "world"
        field.commit()
        XCTAssertFalse(field.isDirty)
        XCTAssertEqual(field.original, "world")
        XCTAssertEqual(field.current, "world")
    }

    func testRollbackDiscardsChanges() {
        var field = Dirtyable("hello")
        field.value = "world"
        field.rollback()
        XCTAssertFalse(field.isDirty)
        XCTAssertEqual(field.current, "hello")
    }

    func testCurrentReturnsUpdatedOrOriginal() {
        var field = Dirtyable("original")
        XCTAssertEqual(field.current, "original")
        field.value = "updated"
        XCTAssertEqual(field.current, "updated")
        field.rollback()
        XCTAssertEqual(field.current, "original")
    }

    // MARK: - Bool (Equatable)

    func testBoolInitiallyNotDirty() {
        let field = Dirtyable(false)
        XCTAssertFalse(field.isDirty)
        XCTAssertEqual(field.current, false)
    }

    func testBoolMutationMarksDirty() {
        var field = Dirtyable(false)
        field.value = true
        XCTAssertTrue(field.isDirty)
        XCTAssertEqual(field.current, true)
    }

    func testBoolRevertClearsDirty() {
        var field = Dirtyable(false)
        field.value = true
        XCTAssertTrue(field.isDirty)
        field.value = false
        XCTAssertFalse(field.isDirty)
    }

    func testCommitWithNoChangeIsNoOp() {
        var field = Dirtyable("unchanged")
        field.commit()
        XCTAssertFalse(field.isDirty)
        XCTAssertEqual(field.current, "unchanged")
    }
}
