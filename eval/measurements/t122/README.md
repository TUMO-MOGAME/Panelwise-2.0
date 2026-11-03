# T122: a page's image links, signed one at a time or in one request (2026-10-19)

Tumo (via Claude), on Tumo's machine (South Africa), in the local API container on main @ `e47c47c`,
against the dev bucket of the shared Supabase project (eu-west-1). Free: signing writes nothing.
Design: [docs/design/storyboard.md](../../../docs/design/storyboard.md) §6, §8, §9 T122.

**`probe_sign.py <project id> 5`** on rooftop-tomatoes (`2f75b732`, 21 accepted frames), 5 rounds:

| | One link per request, one after another (today's `read_frames`) | One batch request |
|---|---|---|
| Rounds (ms) | 5,544 · 4,939 · 4,941 · 4,877 · 4,684 | 223 · 218 · 216 · 225 · 219 |
| Median | **4,939 ms** (235 ms a link) | **219 ms** |

The storyboard page polls every 2 s while frames are drawn, and each poll's `/frames` re-signs
every accepted frame. From here, that's 5 s of signing a poll. Render's Frankfurt server is nearer
to Supabase's Ireland region, so the hosted times are smaller, but the ratio is the same request count.

**`probe_sign_shape.py <project id>`**: what the batch answer looks like.
- 200, a list in the request's order, each `{"error", "path", "signedURL"}`. The link has the
  single call's form (`/object/sign/<bucket>/<path>?token=…`).
- A missing object doesn't fail the request: its item has `"signedURL": null` and an `error`.
- `"paths": []` is refused: 400 "body/paths must NOT have fewer than 1 items". So `signed_urls([])`
  makes no request.

**`probe_sign_dupes.py <project id>`**: asked `[a, b, a]` in one batch.
- 3 answers for 3 paths, each echoing its path in place: the duplicate is signed both times.
- The batch link equals the single call's link up to `?token=`, and fetching it returns the image (200).

**`live_t122.py <project id>`** (after the code, 2026-10-19): the branch's `SupabaseStore.signed_urls`
on rooftop-tomatoes' 21 accepted frames: **1 request** (`POST /storage/v1/object/sign/panelwise-dev`),
21 links in order, all 21 open (200); 866 ms including a fresh connection (the warm batch above: 219 ms).
