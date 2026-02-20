import SwiftUI

struct CommaSeparatedField: View {
    @Binding var items: [String]?
    var placeholder: String = ""
    var normalize: ((String) -> String)? = nil

    @State private var text: String = ""

    var body: some View {
        TextField(placeholder, text: $text)
            .textFieldStyle(.roundedBorder)
            .font(.system(size: 11, design: .monospaced))
            .onAppear { text = (items ?? []).joined(separator: ", ") }
            .onChange(of: text) { _, newValue in
                let parsed = newValue
                    .split(separator: ",")
                    .map { $0.trimmingCharacters(in: .whitespaces) }
                    .filter { !$0.isEmpty }
                    .map { normalize?($0) ?? $0 }
                items = parsed.isEmpty ? nil : parsed
            }
            .onChange(of: items) { _, newValue in
                let current = text
                    .split(separator: ",")
                    .map { $0.trimmingCharacters(in: .whitespaces) }
                    .filter { !$0.isEmpty }
                    .map { normalize?($0) ?? $0 }
                let incoming = newValue ?? []
                if current != incoming {
                    text = incoming.joined(separator: ", ")
                }
            }
    }
}

struct ExtensionField: View {
    @Binding var items: [String]?
    var placeholder: String = ".ext, .ext"

    var body: some View {
        CommaSeparatedField(
            items: $items,
            placeholder: placeholder,
            normalize: { $0.hasPrefix(".") ? $0 : ".\($0)" }
        )
    }
}
