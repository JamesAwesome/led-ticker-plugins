import pytest

from led_ticker_flair.flair import _board_transition as bt
from led_ticker_flair.flair.splitflap import SplitFlap


def test_splitflap_subclasses_board_transition_and_does_not_fork_frame_at():
    assert issubclass(SplitFlap, bt.BoardTransition)
    assert "frame_at" not in SplitFlap.__dict__
    assert "_schedule" not in SplitFlap.__dict__  # splitflap keeps the base ripple


def test_base_paint_is_abstract():
    with pytest.raises(NotImplementedError):
        bt.BoardTransition(0, 0.0)._paint(None, None, 0.0)


@pytest.mark.parametrize("bad", [-1, True, 1.5, "3", 7])
def test_coerce_steps_rejects_with_callers_name(bad):
    with pytest.raises(ValueError, match=r"spins must be an int in \[0, 6\]"):
        bt.coerce_steps(bad, "spins", 6)


def test_coerce_steps_accepts_edges():
    assert bt.coerce_steps(0, "x", 6) == 0 and bt.coerce_steps(6, "x", 6) == 6


def test_splitflap_keeps_its_cap_and_message():
    with pytest.raises(ValueError, match=r"flips must be an int in \[0, 12\]"):
        SplitFlap(flips=13)
    assert SplitFlap(flips=12).flips == 12 and SplitFlap(flips=12).steps == 12


def test_slots_subclasses_board_transition_and_does_not_fork_frame_at():
    from led_ticker_flair.flair.slots import Slots

    assert issubclass(Slots, bt.BoardTransition)
    assert "frame_at" not in Slots.__dict__
    assert "_schedule" in Slots.__dict__ and "_paint" in Slots.__dict__
