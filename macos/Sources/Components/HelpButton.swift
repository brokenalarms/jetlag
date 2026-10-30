import SwiftUI

struct HelpLabel: View {
    let text: String
    let help: String

    init(_ text: String, help: String) {
        self.text = text
        self.help = help
    }

    var body: some View {
        HStack(spacing: Theme.Space.sm) {
            Text(text)
            HelpButton(help)
        }
    }
}

struct HelpButton: View {
    let text: String
    @State private var showHelp = false

    init(_ text: String) {
        self.text = text
    }

    var body: some View {
        Image(systemName: "questionmark.circle")
            .foregroundStyle(Theme.Text.secondary)
            .onTapGesture { showHelp.toggle() }
            .popover(isPresented: $showHelp, arrowEdge: .bottom) {
                Text(text)
                    .font(Theme.Typography.caption)
                    .padding(Theme.Space.xl)
                    .frame(width: Theme.Size.helpPopover, alignment: .leading)
                    .fixedSize(horizontal: false, vertical: true)
            }
    }
}
