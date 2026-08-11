import SwiftUI

struct TimezonePickerView: View {
    @Binding var selectedTimezone: String
    @State private var showingPicker = false

    var body: some View {
        Button {
            showingPicker = true
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "globe")
                if selectedTimezone.isEmpty {
                    Text(Strings.Workflow.selectTimezone)
                        .foregroundStyle(.secondary)

                } else if let option = TimezoneCatalog.option(selectedTimezone) {
                    Text(option.city)
                    Text(option.offset)
                        .font(.system(.body, design: .monospaced))
                        .foregroundStyle(.secondary)
                } else {
                    Text(selectedTimezone)
                        .font(.system(.body, design: .monospaced))
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

    private var filtered: [TimezoneOption] {
        if searchText.isEmpty { return TimezoneCatalog.all }
        let query = searchText.lowercased()
        return TimezoneCatalog.all.filter {
            $0.path.lowercased().contains(query)
                || $0.region.lowercased().contains(query)
                || $0.offset.contains(query)
        }
    }

    private var grouped: [(region: String, items: [TimezoneOption])] {
        Dictionary(grouping: filtered, by: \.region)
            .sorted { $0.key < $1.key }
            .map { (region: $0.key, items: $0.value) }
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
                        ForEach(group.items) { item in
                            Button {
                                selectedTimezone = item.id
                                isPresented = false
                            } label: {
                                HStack {
                                    Text(item.path)
                                        .lineLimit(1)
                                        .fontWeight(item.id == selectedTimezone ? .semibold : .regular)
                                    Spacer()
                                    Text(item.offset)
                                        .font(.system(.caption, design: .monospaced))
                                        .foregroundStyle(.secondary)
                                }
                                .contentShape(Rectangle())

                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
            .listStyle(.plain)
        }
        .frame(width: 250, height: 380)
    }
}
