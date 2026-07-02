# led-ticker-flair

Homage sprite-trail transitions and text animations for [led-ticker](https://github.com/JamesAwesome/led-ticker) — four sprite families plus the propeller animation, all in one wheel.

## Sprite-trail transitions

| Family | Type strings | Notes |
|---|---|---|
| nyancat | `nyancat.forward` / `nyancat.reverse` / `nyancat.alternating` | Hi-res sprite on bigsign |
| pokeball | `pokeball.forward` / `pokeball.reverse` / `pokeball.alternating` | Hi-res sprite + `:pokeball.ball:` emoji |
| pacman | `pacman.forward` / `pacman.reverse` / `pacman.alternating` | Low-res |
| sailor_moon | `sailor_moon.forward` / `sailor_moon.reverse` / `sailor_moon.alternating` | Low-res |

> **Unofficial fan homage.** These sprites are the property of their respective rights holders and are **not** covered by this project's license. Non-commercial homage only; no affiliation or endorsement. See the repo [NOTICE](https://github.com/JamesAwesome/led-ticker-plugins/blob/main/NOTICE.md).

## Propeller animation

`flair.propeller` spins a message widget's text in-plane on visit entry — a full-rotation ease-out that settles flat — then holds the text readable for the rest of the configured hold time. Transitions wait for the spin to finish before starting.

Requires **led-ticker-core >= 4.3**.

### Config

Shorthand (all defaults):

```toml
[[playlist.section.widget]]
type = "message"
text = "Hello!"
animation = "flair.propeller"
```

Inline table with overrides:

```toml
[[playlist.section.widget]]
type = "message"
text = "Hello!"
animation = {style = "flair.propeller", revolutions = 3, spin_seconds = 1.5, direction = "ccw"}
```

### Knobs

| Field | Type | Default | Notes |
|---|---|---|---|
| `revolutions` | int ≥ 1 | `2` | Full rotations completed during the spin-in |
| `spin_seconds` | float > 0 | `1.0` | Wall-clock duration of the spin phase |
| `direction` | `"cw"` / `"ccw"` | `"cw"` | Clockwise or counter-clockwise |

### Caveats

- **Message widgets only.** `flair.propeller` works on `message` widgets (core rejects `animation` on other widget types at config load). GIF / image text-overlay widgets accept `animation` but ignore the rotation.
- **BDF fonts only for now.** Hi-res fonts display normally but the rotation effect is skipped. `led-ticker validate` warns (rule 63) when a propeller widget uses a hi-res font.
- **Short-hold warning.** If `spin_seconds` outlasts `hold_time` the spin is truncated and the text appears only briefly. `led-ticker validate` warns (rule 62). Either raise `hold_time` or lower `spin_seconds` / `revolutions`.
- **Phase resets each visit.** The spin restarts from the beginning every time the widget enters the rotation — it does not continue mid-spin across section cycles.

## Install

Part of the [led-ticker-plugins](https://github.com/JamesAwesome/led-ticker-plugins) monorepo. Install:

```bash
pip install "git+https://github.com/JamesAwesome/led-ticker-plugins.git@flair-v0.1.0#subdirectory=plugins/flair"
```
