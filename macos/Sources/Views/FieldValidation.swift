import SwiftUI

/// Tracks which form fields have been blurred (lost focus) at least once.
/// Fields that have never been blurred should not show validation errors.
///
/// Generic over any `Hashable` field identifier — typically a view-local enum.
@Observable
final class TouchState {
    private var blurred: Set<AnyHashable> = []

    func hasBlurred<F: Hashable>(_ field: F) -> Bool {
        blurred.contains(AnyHashable(field))
    }

    func markBlurred<F: Hashable>(_ field: F) {
        blurred.insert(AnyHashable(field))
    }

    func reset() {
        blurred.removeAll()
    }
}

extension View {
    /// Conditionally appends a validation error label below the view.
    /// Shows nothing when `error` is nil or `show` is false.
    @ViewBuilder
    func fieldError(_ error: String?, show: Bool) -> some View {
        self
        if let error, show {
            Label(error, systemImage: "exclamationmark.triangle.fill")
                .font(.caption)
                .foregroundStyle(.red)
        }
    }
}
