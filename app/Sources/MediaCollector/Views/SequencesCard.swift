import SwiftUI

/// "Entire project" or a hand-picked set of sequences.
struct SequencesCard: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        @Bindable var model = model
        if let project = model.project, !project.sequences.isEmpty {
            Card(title: "Scope", symbol: "film.stack") {
                Picker("", selection: $model.chooseSequences) {
                    Text("Entire project").tag(false)
                    Text("Choose sequences").tag(true)
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .frame(maxWidth: .infinity)

                if model.chooseSequences {
                    if project.sequences.count > 8 {
                        ScrollView { list(project) }.frame(height: 200)  // long lists (a real project has 222) scroll
                    } else {
                        list(project)
                    }
                    if project.sequences.count > 1 {
                        let allSelected = model.selectedSequences.count == project.sequences.count
                        HStack {
                            Text("\(model.selectedSequences.count) of \(project.sequences.count) selected")
                                .font(.callout).foregroundStyle(.secondary)
                            Spacer()
                            Button(allSelected ? "Select None" : "Select All") {
                                model.selectedSequences = allSelected ? [] : Set(project.sequences.map(\.id))
                            }
                            .buttonStyle(.link)
                            .font(.callout)
                        }
                    }
                }
            }
        }
    }

    private func list(_ project: ProjectSummary) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            ForEach(project.sequences) { seq in
                Toggle(isOn: binding(for: seq.id)) {
                    HStack {
                        Text(seq.name.isEmpty ? "Untitled sequence" : seq.name).lineLimit(1)
                        Spacer()
                        Text("\(seq.originals) files").foregroundStyle(.secondary).font(.callout)
                    }
                }
                .toggleStyle(.checkbox)
            }
        }
    }

    private func binding(for id: String) -> Binding<Bool> {
        Binding(
            get: { model.selectedSequences.contains(id) },
            set: { on in
                if on { model.selectedSequences.insert(id) } else { model.selectedSequences.remove(id) }
            })
    }
}
