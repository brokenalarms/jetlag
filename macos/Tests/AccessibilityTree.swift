import AppKit

/// SwiftUI builds a hosted view's accessibility tree only once an assistive client asks
/// for it, so tests that read the tree passed on a machine with such a client attached
/// and found an empty tree everywhere else. Asking for it here makes those tests
/// independent of what else is running.
enum AccessibilityTree {
    /// The call reports `attributeUnsupported` even though the tree is built, so its
    /// result says nothing and is ignored.
    static func setBuilt(_ built: Bool) {
        _ = AXUIElementSetAttributeValue(
            AXUIElementCreateApplication(getpid()),
            "AXManualAccessibility" as CFString,
            built ? kCFBooleanTrue : kCFBooleanFalse)
    }

    /// Every node beneath `element`, depth first. The nodes answer the accessibility
    /// methods without declaring the protocol, so they are called dynamically.
    static func nodes(in element: AnyObject) -> [AnyObject] {
        let children = (element.accessibilityChildren?() ?? nil) ?? []
        return [element] + children.flatMap { nodes(in: $0 as AnyObject) }
    }
}
