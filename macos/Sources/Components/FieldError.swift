import SwiftUI

extension View {
    @ViewBuilder
    func fieldError(_ error: String?) -> some View {
        self
        if let error {
            Label(error, systemImage: "exclamationmark.triangle.fill")
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Status.failure)
        }
    }
}
