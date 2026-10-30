import XCTest
import SwiftUI
import AppKit
@testable import Jetlag

/// The form components take plain data so that any screen can use them. These tests host
/// each one on its own, with no PipelineStep or session, and read what it actually exposes
/// through the accessibility tree: which controls exist, whether they are enabled, and what
/// pressing them does.
final class ComponentsTests: XCTestCase {

    override func setUp() {
        AccessibilityTree.setBuilt(true)
    }

    override func tearDown() {
        AccessibilityTree.setBuilt(false)
    }

    private func host<V: View>(_ view: V, width: CGFloat = 600) -> NSHostingView<V> {
        let host = NSHostingView(rootView: view)
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: width, height: 300),
                              styleMask: [.titled], backing: .buffered, defer: false)
        window.contentView = host
        host.frame = NSRect(x: 0, y: 0, width: width, height: 300)
        host.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.2))
        host.layoutSubtreeIfNeeded()
        return host
    }

    private func nodes(_ role: NSAccessibility.Role, in view: NSView) -> [AnyObject] {
        AccessibilityTree.nodes(in: view).filter { $0.accessibilityRole?() == role }
    }

    private func button(_ title: String, in view: NSView) -> AnyObject? {
        nodes(.button, in: view).first { $0.accessibilityLabel?() == title }
    }

    private func texts(in view: NSView) -> [String] {
        nodes(.staticText, in: view).compactMap { node in
            let value: Any?? = node.accessibilityValue?()
            return (value ?? nil) as? String
        }
    }

    private func card(isRequired: Bool, isActive: Bool, onToggle: @escaping () -> Void = {}) -> some View {
        Card(title: "Step", icon: "folder", tint: .blue, help: "Help",
             isRequired: isRequired, isActive: isActive, onToggle: onToggle) {
            Text("Card body")
        }
    }

    /// An optional card's header is the control that turns it on and off.
    func testOptionalCardHeaderPressCallsOnToggle() {
        var toggles = 0
        let hosted = host(card(isRequired: false, isActive: false) { toggles += 1 })
        XCTAssertEqual(button("Step", in: hosted)?.accessibilityPerformPress?(), true)
        XCTAssertEqual(toggles, 1)
    }

    /// A required step cannot be turned off, so its header is not a button at all: it
    /// says Required instead.
    func testRequiredCardHeaderIsNotAControl() {
        let hosted = host(card(isRequired: true, isActive: true))
        XCTAssertNil(button("Step", in: hosted))
        XCTAssertTrue(texts(in: hosted).contains(Strings.Workflow.requiredLabel))
    }

    /// An inactive card is a header alone: its options are not part of the form.
    func testCardShowsItsBodyOnlyWhileActive() {
        XCTAssertTrue(texts(in: host(card(isRequired: false, isActive: true))).contains("Card body"))
        XCTAssertFalse(texts(in: host(card(isRequired: false, isActive: false))).contains("Card body"))
    }

    /// Wide enough, every chip shows its label with a chevron between each pair; too
    /// narrow, the labels give way and the chips and chevrons remain.
    func testChipBarCollapsesLabelsWhenNarrow() {
        let chips = ["One", "Two", "Three"].map { Chip(id: $0, icon: "folder", label: $0, tint: .blue) }
        func chevrons(in view: NSView) -> Int {
            nodes(.image, in: view).filter { $0.accessibilityLabel?() == "Forward" }.count
        }

        let wide = host(ChipBar(chips: chips))
        XCTAssertEqual(texts(in: wide), ["One", "Two", "Three"])
        XCTAssertEqual(chevrons(in: wide), 2)

        let narrow = host(ChipBar(chips: chips), width: 120)
        XCTAssertEqual(texts(in: narrow), [])
        XCTAssertEqual(chevrons(in: narrow), 2)
    }

    /// The validation error is shown under the field only while there is one.
    func testPathFieldShowsItsErrorOnlyWhenThereIsOne() {
        func field(error: String?) -> some View {
            PathField(placeholder: "Path", path: .constant(""), error: error)
        }
        XCTAssertTrue(texts(in: host(field(error: "No such folder"))).contains("No such folder"))
        XCTAssertFalse(texts(in: host(field(error: nil))).contains("No such folder"))
        XCTAssertNotNil(button(Strings.Common.browse, in: host(field(error: nil))))
    }

    /// With a label width, rows with different labels line their controls up in one column.
    func testOptionRowsLineUpTheirControlsAtAFixedLabelWidth() {
        let hosted = host(VStack(alignment: .leading) {
            OptionRow(label: "A", labelWidth: Theme.Size.optionLabel) { Button("First") {} }
            OptionRow(label: "Camera", labelWidth: Theme.Size.optionLabel) { Button("Second") {} }
        })
        let first = button("First", in: hosted)?.accessibilityFrame?().minX
        let second = button("Second", in: hosted)?.accessibilityFrame?().minX
        XCTAssertNotNil(first)
        XCTAssertEqual(first, second)
    }

    /// The checkbox writes its binding, unless the row is disabled.
    func testToggleRowWritesItsBindingOnlyWhileEnabled() {
        var isOn = false
        let binding = Binding(get: { isOn }, set: { isOn = $0 })

        let enabled = host(ToggleRow(title: "Option", caption: "Detail", isOn: binding))
        XCTAssertEqual(nodes(.checkBox, in: enabled).first?.isAccessibilityEnabled?(), true)
        XCTAssertEqual(nodes(.checkBox, in: enabled).first?.accessibilityPerformPress?(), true)
        XCTAssertTrue(isOn)

        let disabled = host(ToggleRow(title: "Option", isOn: binding, isEnabled: false))
        XCTAssertEqual(nodes(.checkBox, in: disabled).first?.isAccessibilityEnabled?(), false)
    }

    private func actionBar(isRunning: Bool, canRun: Bool,
                           onRun: @escaping () -> Void = {}, onCancel: @escaping () -> Void = {}) -> some View {
        ActionBar(modes: [ActionMode(title: "Preview", value: false), ActionMode(title: "Commit", value: true)],
                  mode: .constant(false), primaryTitle: "Go", cancelTitle: "Stop",
                  isRunning: isRunning, canRun: canRun, onRun: onRun, onCancel: onCancel)
    }

    /// Idle, the primary button runs and there is nothing to cancel.
    func testActionBarRunsWhenIdle() {
        var runs = 0
        let hosted = host(actionBar(isRunning: false, canRun: true, onRun: { runs += 1 }))
        XCTAssertEqual(button("Go", in: hosted)?.accessibilityPerformPress?(), true)
        XCTAssertEqual(runs, 1)
        XCTAssertNil(button("Stop", in: hosted))
    }

    /// A form that is not ready cannot be run.
    func testActionBarPrimaryIsDisabledUntilItCanRun() {
        let hosted = host(actionBar(isRunning: false, canRun: false))
        XCTAssertEqual(button("Go", in: hosted)?.isAccessibilityEnabled?(), false)
    }

    /// While running, the primary button is inert and Cancel is the one live control.
    func testActionBarOffersCancelWhileRunning() {
        var cancels = 0
        let hosted = host(actionBar(isRunning: true, canRun: true, onCancel: { cancels += 1 }))
        XCTAssertEqual(button("Go", in: hosted)?.isAccessibilityEnabled?(), false)
        XCTAssertEqual(button("Stop", in: hosted)?.accessibilityPerformPress?(), true)
        XCTAssertEqual(cancels, 1)
    }

    /// Clicking an optional step's card header turns the step on and off in the session,
    /// and with it the card's options. A required step has no such control, and the
    /// session refuses to turn one off whoever asks.
    func testStepToggling() {
        let state = AppState()
        state.selectedTab = .workflow
        state.workflowSession = WorkflowSession(profileName: "probe", gyroflowAvailable: false)
        let hosted = host(WorkflowView(state: state), width: WorkflowView.formWidth)
        let session = state.workflowSession

        XCTAssertFalse(session.enabledSteps.contains(.archiveSource))
        XCTAssertEqual(button(PipelineStep.archiveSource.label, in: hosted)?.accessibilityPerformPress?(), true)
        XCTAssertTrue(session.enabledSteps.contains(.archiveSource))

        session.toggle(.archiveSource)
        XCTAssertFalse(session.enabledSteps.contains(.archiveSource))

        XCTAssertTrue(PipelineStep.ingest.isAlwaysOn)
        XCTAssertNil(button(PipelineStep.ingest.label, in: hosted))
        session.enabledSteps.insert(.ingest)
        session.toggle(.ingest)
        XCTAssertTrue(session.enabledSteps.contains(.ingest))
    }
}
