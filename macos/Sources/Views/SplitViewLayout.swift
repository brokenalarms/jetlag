import SwiftUI

/// Every width the three-column split view negotiates, declared once.
///
/// The split view can only settle if each column has a single legal answer for the
/// window width it is given. The workflow form is a stack of fixed-width controls, so
/// the detail column is sized to hold exactly that form and nothing else; the sidebar
/// keeps its own fixed range; the inspector absorbs whatever is left. When the numbers
/// are separate literals they stop adding up — a window minimum narrower than
/// sidebar + form + inspector leaves AppKit no solution once the inspector opens, and it
/// re-runs the negotiation on every resize until the update-constraints pass is aborted.
enum SplitViewLayout {
    static let sidebarMinWidth: CGFloat = 140
    static let sidebarIdealWidth: CGFloat = 160

    /// The workflow form's own width. It never grows and is never squeezed: the controls
    /// inside are fixed-size, so any other width either clips them or leaves dead space.
    static let formContentWidth: CGFloat = 600
    static let formHorizontalPadding: CGFloat = 16

    /// The detail column holds the form plus its gutters, and has no maximum — the
    /// split view is free to hand it more, but it never needs more.
    static let detailMinWidth = formContentWidth + formHorizontalPadding * 2

    static let inspectorMinWidth: CGFloat = 480
    static let inspectorIdealWidth: CGFloat = 600

    static let windowMinHeight: CGFloat = 800

    /// The narrowest window in which all visible columns fit side by side. Declared as
    /// the content's minimum size so `windowResizability(.contentMinSize)` grows the
    /// window when the inspector opens instead of overlapping the columns.
    static func windowMinWidth(inspectorVisible: Bool) -> CGFloat {
        sidebarMinWidth + detailMinWidth + (inspectorVisible ? inspectorMinWidth : 0)
    }
}
