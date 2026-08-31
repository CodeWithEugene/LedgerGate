# Brand assets

The mark is a shield — the gate — with ruled ledger lines cut through it. One
of those lines stops short. That is the whole product in a glyph: the system
reads the ledger, and one line does not get written.

All files are PNG with a transparent surround. There is no white box behind
any of them.

| File | Use |
| --- | --- |
| `logo-mark.png` | 512px mark, navy. For light surfaces. |
| `logo-mark-light.png` | 512px mark, white. For dark surfaces. |
| `logo-wordmark.png` | Horizontal lockup, navy. For light surfaces. |
| `logo-wordmark-light.png` | Horizontal lockup, white. For dark surfaces. |

The application's copies live in [`web/public/`](../../web/public/), alongside
the derived favicon set.

## Two colours, and why the files are so small

Deep navy `#0F172A` and white. Nothing else — no gradient, no shadow, no
third accent. Every asset is flattened to exactly those two values before it
is written, which is also why a 512px icon is 13 KB rather than 111 KB: the
generator leaves a haze of near-navy tones that are invisible at full size,
blur the edges when downsampled to 32px, and compress terribly.

## Transparency is not one decision

Two different rules apply, and using either one everywhere produces a subtly
broken logo.

The **mark is a knockout**: its ledger rules are cut through the shield. Those
cut-outs have to stay *opaque white*. Make them transparent and the shield
stops being a shield the moment it sits on anything that is not white — the
rules simply fill in with the background. So only the border-connected
surround is cleared.

The **wordmark is type**. The counters — the enclosed whites inside `e`, `d`,
`g`, `a` — have to be *transparent*, or every letter looks like it was filled
in with correction fluid as soon as the logo leaves a white page.

The lockup contains both, so it is split at the gap between the shield and the
first letter and each half is treated on its own terms.

## Light and dark are shipped separately

A CSS filter cannot recolour a knockout mark: `invert()` flips the rules along
with the shield, and a tint cannot distinguish the two. So each mark exists as
two files and the correct one is selected — by `dark:` variant in the sidebar,
and by `media="(prefers-color-scheme: dark)"` on the favicon links.

The Apple touch icon is the **white** mark. iOS composites a transparent icon
onto black, so shipping the navy one would put an invisible app on the home
screen.

## Regenerating

The artwork was produced with an image model and post-processed; the sources
are in `assets/` outside the repository. Nothing in `make verify` reads these
files, and no build step regenerates them — they are committed artifacts, and
replacing them is a manual design decision rather than something a pipeline
should quietly redo.
