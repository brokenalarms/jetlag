import XCTest
import SwiftUI
import AppKit
@testable import Jetlag

/// "Include network locations" only means something as part of a hash check, so the
/// form shows it as part of "Verify hashes": indented beneath it, and dimmed until
/// hashes are on. A sibling toggle that does nothing when switched on reads as broken;
/// a hidden one makes the form jump and hides what the check can do.
final class VerifyFormTests: XCTestCase {

    override func setUp() {
        AccessibilityTree.setBuilt(true)
    }

    override func tearDown() {
        AccessibilityTree.setBuilt(false)
    }

    private func host(_ state: AppState) -> NSHostingView<VerifyView> {
        let host = NSHostingView(rootView: VerifyView(state: state))
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: WorkflowView.formWidth, height: 900),
                              styleMask: [.titled], backing: .buffered, defer: false)
        window.contentView = host
        host.frame = NSRect(x: 0, y: 0, width: WorkflowView.formWidth, height: 900)
        HostedWindow.settle(host)
        HostedWindow.settle(host)
        return host
    }

    private func textFrames(in view: NSView) -> [String: NSRect] {
        var frames: [String: NSRect] = [:]
        for node in AccessibilityTree.nodes(in: view) where node.accessibilityRole?() == .staticText {
            let value: Any?? = node.accessibilityValue?()
            if let text = (value ?? nil) as? String, let frame = node.accessibilityFrame?() {
                frames[text] = frame
            }
        }
        return frames
    }

    /// The switch on the same line as a label: SwiftUI exposes the toggle's label and its
    /// switch as separate nodes.
    private func switchEnabled(besideText text: String, in view: NSView) throws -> Bool {
        let label = try XCTUnwrap(textFrames(in: view)[text])
        let node = try XCTUnwrap(AccessibilityTree.nodes(in: view).first { node in
            guard node.accessibilityRole?() == .checkBox, let frame = node.accessibilityFrame?() else { return false }
            return frame.minY <= label.midY && label.midY <= frame.maxY
        })
        return node.isAccessibilityEnabled?() ?? false
    }

    func testNetworkToggleIsIndentedUnderVerifyHashesAndDimmedUntilItIsOn() throws {
        let state = AppState()
        let off = host(state)
        let frames = textFrames(in: off)
        let hashes = try XCTUnwrap(frames[Strings.Verify.verifyHashes])
        let network = try XCTUnwrap(frames[Strings.Verify.includeNetwork])
        XCTAssertGreaterThan(network.minX, hashes.minX)
        XCTAssertLessThan(network.maxY, hashes.minY, "below it, in screen coordinates")
        XCTAssertFalse(try switchEnabled(besideText: Strings.Verify.includeNetwork, in: off))

        state.verifySession.verifyHashes = true
        XCTAssertTrue(try switchEnabled(besideText: Strings.Verify.includeNetwork, in: host(state)))
    }
}
