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
                    Text(option.offsetLabel)
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

    private var filtered: [(option: TimezoneOption, match: TimezoneMatch)] {
        TimezoneCatalog.all.compactMap { option in
            let match = searchText.isEmpty ? TimezoneMatch(place: nil) : option.match(searchText)
            return match.map { (option, $0) }
        }
    }

    private var grouped: [(region: String, items: [(option: TimezoneOption, match: TimezoneMatch)])] {
        Dictionary(grouping: filtered, by: \.option.region)
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
                        ForEach(group.items, id: \.option.id) { result in
                            let item = result.option
                            Button {
                                selectedTimezone = item.id
                                isPresented = false
                            } label: {
                                HStack {
                                    VStack(alignment: .leading, spacing: 0) {
                                        Text(item.path)
                                            .lineLimit(1)
                                            .fontWeight(item.id == selectedTimezone ? .semibold : .regular)
                                        if let place = result.match.place {
                                            Text(place)
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                                .lineLimit(1)
                                        }
                                    }
                                    Spacer()
                                    Text(item.offsetLabel)
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
