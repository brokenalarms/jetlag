import SwiftUI

struct TimezonePickerView: View {
    @Binding var selectedTimezone: String
    @State private var showingPicker = false

    fileprivate static let timezones: [(id: String, label: String, offset: String)] = {
        TimeZone.knownTimeZoneIdentifiers.sorted().compactMap { id in
            guard let tz = TimeZone(identifier: id) else { return nil }
            let seconds = tz.secondsFromGMT()
            let sign = seconds >= 0 ? "+" : "-"
            let abs = abs(seconds)
            let h = abs / 3600
            let m = (abs % 3600) / 60
            let offset = String(format: "%@%02d%02d", sign, h, m)
            let label = id.replacingOccurrences(of: "_", with: " ")
            return (id: id, label: label, offset: offset)
        }
    }()

    var body: some View {
        Button {
            showingPicker = true
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "globe")
                if selectedTimezone.isEmpty {
                    Text(Strings.Workflow.selectTimezone)
                        .foregroundStyle(.secondary)
                } else {
                    let match = Self.timezones.first { $0.offset == selectedTimezone }
                    if let match {
                        Text(match.label.components(separatedBy: "/").last ?? match.label)
                        Text(match.offset)
                            .font(.system(.body, design: .monospaced))
                            .foregroundStyle(.secondary)
                    } else {
                        Text(selectedTimezone)
                            .font(.system(.body, design: .monospaced))
                    }
                }
                Image(systemName: "chevron.up.chevron.down")
                    .font(.system(size: 9))
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .frame(minWidth: 180)
            .background(.background)
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .strokeBorder(.separator, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .sheet(isPresented: $showingPicker) {
            TimezonePickerSheet(
                selectedTimezone: $selectedTimezone,
                isPresented: $showingPicker
            )
        }
    }
}

private struct TimezonePickerSheet: View {
    @Binding var selectedTimezone: String
    @Binding var isPresented: Bool
    @State private var searchText = ""

    private var filtered: [(id: String, label: String, offset: String)] {
        if searchText.isEmpty { return TimezonePickerView.timezones }
        let query = searchText.lowercased()
        return TimezonePickerView.timezones.filter {
            $0.label.lowercased().contains(query) || $0.offset.contains(query)
        }
    }

    private var grouped: [(region: String, items: [(id: String, label: String, offset: String)])] {
        let dict = Dictionary(grouping: filtered) { entry in
            entry.id.components(separatedBy: "/").first ?? "Other"
        }
        return dict.sorted { $0.key < $1.key }.map { (region: $0.key, items: $0.value) }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                TextField(Strings.Workflow.searchTimezones, text: $searchText)
                    .textFieldStyle(.plain)
                Spacer()
                Button(Strings.Common.done) {
                    isPresented = false
                }
            }
            .padding(8)

            Divider()

            List {
                ForEach(grouped, id: \.region) { group in
                    Section(group.region) {
                        ForEach(group.items, id: \.id) { item in
                            Button {
                                selectedTimezone = item.offset
                                isPresented = false
                            } label: {
                                HStack {
                                    Text(item.label.components(separatedBy: "/").dropFirst().joined(separator: " / "))
                                        .lineLimit(1)
                                    Spacer()
                                    Text(item.offset)
                                        .font(.system(.caption, design: .monospaced))
                                        .foregroundStyle(.secondary)
                                }
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
            .listStyle(.plain)
        }
        .frame(width: 320, height: 380)
    }
}
