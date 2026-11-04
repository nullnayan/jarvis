# FILE: backend/tools/gesture_tool.py
# Controls 3D hand gesture tracking and fullscreen mode via voice commands.

_pipeline_ref = None

def set_pipeline(pipeline):
    global _pipeline_ref
    _pipeline_ref = pipeline

def gesture_control(params: dict) -> str:
    action = str(params.get("action", "enable")).lower()
    if _pipeline_ref:
        if action in ("enable", "on", "start", "activate", "true", "open"):
            _pipeline_ref.start_gesture_tracking()
            from server.messages import fullscreen_toggle_msg
            _pipeline_ref.send(fullscreen_toggle_msg(True))
            return "Gesture mode enabled, boss."
        else:
            _pipeline_ref.stop_gesture_tracking()
            from server.messages import fullscreen_toggle_msg
            _pipeline_ref.send(fullscreen_toggle_msg(False))
            return "Gesture mode disabled, boss."
    return "Gesture mode updated, boss."
