# After Effects `.aep` — findings

Status: **read-only support implemented** (`src/media_collector/readers/aep.py`); relinking not implemented. Checked on
one real project (`a local sample project`, 10 footage items) and one small one.

- An `.aep` is a **RIFX** file (big-endian RIFF variant): header `RIFX <size> Egg!` then nested chunks
  (`svap`, `head`, `opti`, ...).
- Each footage item stores its location as a small **JSON record** inside a chunk, e.g.
  `{"ascendcount_base":1,"ascendcount_target":3,"fullpath":"/Users/example/.../a.mov","platform":2,"server_name":"","server_volume_name":"","target_is_folder":false}`.
  The reader finds these by pattern (`{"ascendcount_base"...}`) without decoding the chunk tree.
  `platform` 2 = macOS on the samples seen; Windows values not yet seen.
- `ascendcount_base` / `ascendcount_target` look like relative-path hints (levels up from the project);
  their exact meaning is unknown, which matters for relinking.
- Not read: which compositions use which footage (everything counts as used, and the project reports no
  sequences, so the app hides its Scope choice and shows no warning), composition names,
  image-sequence flags, proxies, other reference kinds (placeholders, solids), `.aepx` (XML export).

## To relink (not done)
The JSON record length changes when a path changes, so the enclosing chunk size and every parent chunk
size up to the root must be rewritten (chunks are padded to even length). Doable with a proper RIFX tree
parser; must be tested by opening the result in After Effects (also to learn what the `ascendcount_*`
fields need to be).
