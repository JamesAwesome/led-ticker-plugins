"""flair.fisheye — scrolling text through a stationary squeeze-and-bulge lens."""

from led_ticker.plugin import AnimationFrame, LensSpec


class Fisheye:
    restart_on_visit = False  # stateless — nothing to restart
    emits_rotation = False
    emits_lens = True  # rule-64 duck-type marker (rule-63 pattern)

    def __init__(
        self,
        magnify: float = 1.3,
        edge_squeeze: float = 0.6,
        profile: str = "cosine",
    ) -> None:
        try:
            self._spec = LensSpec(
                magnify=magnify, edge_squeeze=edge_squeeze, profile=profile
            )
        except ValueError as exc:
            raise ValueError(f"flair.fisheye: {exc}") from exc

    def frame_for(self, frame, full_text, canvas_width, text_width):
        return AnimationFrame(visible_text=full_text, lens=self._spec)

    def frames_to_rest(self, frame, total_chars):
        return 0  # cuttable any instant — the lens has no phase
