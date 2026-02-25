import XCTest
@testable import Jetlag

final class TouchStateTests: XCTestCase {

    private enum TestField: Hashable {
        case name
        case email
    }

    func testInitiallyNoFieldsBlurred() {
        let touch = TouchState()
        XCTAssertFalse(touch.hasBlurred(TestField.name))
        XCTAssertFalse(touch.hasBlurred(TestField.email))
    }

    func testMarkBlurredMakesFieldBlurred() {
        let touch = TouchState()
        touch.markBlurred(TestField.name)
        XCTAssertTrue(touch.hasBlurred(TestField.name))
        XCTAssertFalse(touch.hasBlurred(TestField.email))
    }

    func testMarkBlurredIsIdempotent() {
        let touch = TouchState()
        touch.markBlurred(TestField.name)
        touch.markBlurred(TestField.name)
        XCTAssertTrue(touch.hasBlurred(TestField.name))
    }

    func testResetClearsAllFields() {
        let touch = TouchState()
        touch.markBlurred(TestField.name)
        touch.markBlurred(TestField.email)
        touch.reset()
        XCTAssertFalse(touch.hasBlurred(TestField.name))
        XCTAssertFalse(touch.hasBlurred(TestField.email))
    }

    func testDifferentEnumTypesAreIndependent() {
        enum OtherField: Hashable { case alpha }
        let touch = TouchState()
        touch.markBlurred(TestField.name)
        XCTAssertFalse(touch.hasBlurred(OtherField.alpha))
    }
}
