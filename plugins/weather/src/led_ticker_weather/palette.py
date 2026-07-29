"""Semantic palette from design/README.md Design Tokens.

Values are the handoff table's 0-255 RGB verbatim. The handoff's own 0-1
normalization is prototype-engine-specific (its framebuffer stores 0-1)
and deliberately does NOT port — core takes 0-255.

Glyph-drawing tokens (sun/moon/cloud/rain/snow/bolt) do not port either:
icon colors come from the packaged emoji sprites themselves (spec
divergence 1).
"""

RGB = tuple[int, int, int]

IDENT: RGB = (255, 255, 255)  # current temp / neutral text
LABEL: RGB = (70, 90, 130)  # dim labels, dividers, low precip, hi/lo slash
AMBER: RGB = (255, 180, 0)  # day labels
HI: RGB = (255, 148, 36)  # high temp (warm)
LO: RGB = (70, 180, 255)  # low temp (cool)
CYAN: RGB = (0, 200, 255)  # FEELS line, precip >= 50%
