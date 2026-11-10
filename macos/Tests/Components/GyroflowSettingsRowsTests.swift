import XCTest
import SwiftUI
import AppKit
@testable import Jetlag

/// Both the Profiles and Workflow screens edit gyroflow settings through GyroflowSettingsRows.
/// A profile with no settings yet must gain them the moment the user edits a value.
final class GyroflowSettingsRowsTests: XCTestCase {

    private func host(settings: Binding<StabilizationSettings?>) -> NSWindow {
        let host = NSHostingView(rootView: OptionGroup { GyroflowSettingsRows(settings: settings) })
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 600, height: 300),
                              styleMask: [.titled], backing: .buffered, defer: false)
        window.contentView = host
        host.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.2))
        host.layoutSubtreeIfNeeded()
        return window
    }

    private func textFields(in view: NSView) -> [NSTextField] {
        let own = (view as? NSTextField).map { [$0] } ?? []
        return own + view.subviews.flatMap(textFields(in:))
    }

    /// Typing a max zoom into a profile that has no gyroflow settings creates them.
    func testEditingMaxZoomOnNilSettingsCreatesSettings() throws {
        var settings: StabilizationSettings?
        let window = host(settings: Binding(get: { settings }, set: { settings = $0 }))
        let field = try XCTUnwrap(textFields(in: try XCTUnwrap(window.contentView)).first)
        window.makeFirstResponder(field)
        field.currentEditor()?.insertText("125")
        field.currentEditor()?.insertNewline(nil)
        RunLoop.main.run(until: Date().addingTimeInterval(0.2))
        XCTAssertEqual(settings?.maxZoom, 125)
    }

    /// The zoom method is read as Dynamic until the user chooses another.
    func testUnsetZoomMethodReadsAsDynamic() {
        XCTAssertEqual(GyroflowSettingsRows.zoomMethod(of: nil), .dynamic)
        XCTAssertEqual(GyroflowSettingsRows.zoomMethod(of: StabilizationSettings(adaptiveZoomMethod: 2)),
                       AdaptiveZoomMethod(rawValue: 2))
    }
}
