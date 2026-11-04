from tools.computer_use import window_rect_to_header_button


def test_window_relative_header_buttons_use_absolute_window_coordinates():
    rect = (1920, 100, 2920, 900)
    assert window_rect_to_header_button(rect, "voice") == (2746, 162)
    assert window_rect_to_header_button(rect, "video") == (2792, 162)
