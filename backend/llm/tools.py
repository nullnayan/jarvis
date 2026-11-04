# FILE: tools.py
# Tool registry for the multi-model architecture.
# Fast, direct tools live here. Everything else is handled by the coder model or search model.
import json
from llm.code_executor import execute_code
from tools.web_search import web_search
from tools.system_power import system_power
from tools.whatsapp import whatsapp_message, whatsapp_call, whatsapp_video_call, whatsapp_open, whatsapp_take_call
from tools.volume_control import volume_control
from tools.screenshot import screenshot
from tools.clipboard import clipboard
from tools.datetime_tool import get_datetime
from tools.weather import get_weather
from tools.timer import set_timer
from tools.brightness_control import brightness_control
from tools.bluetooth_control import bluetooth_control
from tools.media_control import media_control
from tools.battery_tool import get_battery_status
from tools.wifi_control import wifi_control
from tools.performance_control import performance_control
from tools.datetime_control import datetime_control
from tools.vpn_control import vpn_control
from tools.gesture_tool import gesture_control
from tools.image_generator import generate_image
from tools.video_tool import video_tool
from tools.persistent_memory import persistent_memory
from tools.doc_reader import doc_reader
from tools.code_reviewer import code_reviewer
from tools.youtube_intel import youtube_intel
from tools.system_health import system_health
from tools.clipboard_history import clipboard_history
from tools.routines import routines_tool
from tools.scheduler import scheduler_tool
from tools.music_control import music_control
from tools.system_command import run_shell_command
from tools.security_settings import security_settings
from tools.self_code import self_code
from tools.self_audit import self_audit
from tools.self_fix import self_fix
from tools.computer_use import computer_use
from tools.app_launcher import open_app, open_website, close_app
from tools.youtube import youtube_play
from tools.product_search import product_search
from tools.deal_hunter import deal_hunter
from tools.phone_link import phone_connect, phone_disconnect, phone_status, phone_mirror, phone_screencap, phone_open_app, phone_action, phone_call

TOOL_DEFINITIONS = [
    {
        "name": "product_search",
        "description": "Search for a product on flipkart or amazon india and get its current price and specs",
        "params": {"query": "string - the product to search for"}
    },
    {
        "name": "deal_hunter",
        "description": "Manage the background deal hunter that monitors product prices. Can toggle it on/off, set pincodes, or check its status.",
        "params": {"action": "string - 'status', 'enable', 'disable', 'set_pincodes'", "pincodes": "optional string list of pincodes separated by commas"}
    },
    {
        "name": "product_search",
        "description": "Search for products on Amazon India and Flipkart with real-time accurate prices. Use for any product search — phones, laptops, earbuds, TWS, anything. Returns real prices from actual websites.",
        "params": {
            "query": "string - search query like 'phones under 30000', 'best earbuds under 10000'",
            "max_price": "number - optional max budget in rupees",
            "platform": "string - 'amazon', 'flipkart', or 'both' (default: 'both')"
        }
    },
    {
        "name": "deal_hunter",
        "description": "Manage product deal monitoring and notifications. Start/stop the Deal Hunter, pause/resume specific categories (phone/laptop), add new product watches, update card offers, set pincodes. Use when user wants to control deal notifications.",
        "params": {
            "action": "string - 'start', 'stop', 'watch', 'unwatch', 'pause', 'resume', 'list', 'status', 'update_offers', 'set_pincodes'",
            "category": "string - 'phone', 'laptop', or custom category name",
            "query": "string - search query (for watch)",
            "max_price": "number - max effective price (for watch)",
            "specs": "string - spec requirements or card offer description",
            "interval_hours": "number - hours between checks (default 2)",
            "target": "string - 'all' or category name (for pause/resume/unwatch)",
            "pincodes": "string - comma-separated delivery pincodes supplied by the user"
        }
    },
    {
        "name": "get_datetime",
        "description": "Get the current date, time, and day of the week",
        "params": {}
    },
    {
        "name": "get_weather",
        "description": "Get current weather for a city (defaults to London)",
        "params": {"city": "string - city name (optional, defaults to London)"}
    },
    {
        "name": "get_battery_status",
        "description": "Check the battery percentage and charging status",
        "params": {}
    },
    {
        "name": "volume_control",
        "description": "Set system volume level, increase, decrease, or mute/unmute",
        "params": {"action": "string - 'up', 'down', 'mute', 'unmute', or a number 0-100"}
    },
    {
        "name": "brightness_control",
        "description": "Control screen brightness (increase, decrease, set to a percentage, or check level)",
        "params": {"action": "string - 'up', 'down', 'max', 'min', 'status', or a number 0-100 like '50'"}
    },
    {
        "name": "bluetooth_control",
        "description": "Turn Bluetooth on or off, toggle it, check status, or open settings",
        "params": {"action": "string - 'on', 'off', 'toggle', 'status', or 'settings'"}
    },
    {
        "name": "wifi_control",
        "description": "Turn Wi-Fi on or off, check connection status, scan networks, or connect to a known or new network",
        "params": {
            "action": "string - 'on', 'off', 'status', 'disconnect', 'list', 'connect'",
            "network": "string - network SSID (required for connect)",
            "password": "string - password for new networks (optional)"
        }
    },
    {
        "name": "performance_control",
        "description": "Control display refresh rate in Hz, Windows power plans, and battery saver mode",
        "params": {
            "action": "string - 'refresh_rate', 'power_plan', 'battery_saver', 'get_refresh_rate'",
            "value": "string - '60', '144', 'balanced', 'high_performance', 'power_saver', 'on', 'off'"
        }
    },
    {
        "name": "datetime_control",
        "description": "Set system date/time to automatic sync, change date or time manually, or randomize time",
        "params": {
            "action": "string - 'auto', 'random', 'set', 'get'",
            "value": "string - target datetime string if manual set"
        }
    },
    {
        "name": "vpn_control",
        "description": "Control Proton VPN: connect to fastest or specific country, disconnect, or open",
        "params": {
            "action": "string - 'connect', 'disconnect', 'status', 'open'",
            "country": "string - optional country name like 'Japan', 'US', 'Netherlands'"
        }
    },
    {
        "name": "media_control",
        "description": "Control currently playing media/music (play, pause, next track, previous track, stop)",
        "params": {"action": "string - 'play', 'pause', 'playpause', 'next', 'previous', 'stop'"}
    },
    {
        "name": "open_app",
        "description": "Open/launch any installed application or game by name (Chrome, Valorant, Notepad, VS Code, Spotify, etc.) — searches Start Menu, Desktop shortcuts, and aliases automatically",
        "params": {"app": "string - name of the application to open"}
    },
    {
        "name": "close_app",
        "description": "Close/quit a running application by name (terminates matching processes)",
        "params": {"app": "string - name of the application to close"}
    },
    {
        "name": "open_website",
        "description": "Open a website URL in the default or a specific browser (Chrome, Brave, Edge)",
        "params": {"url": "string - website URL or domain (e.g. 'gmail.com', 'youtube.com')", "browser": "string - optional browser: 'chrome', 'brave', 'edge'"}
    },
    {
        "name": "youtube_play",
        "description": "Open YouTube, or search YouTube and play the first matching video/song in the browser",
        "params": {"query": "string - optional song/video name to search and play; empty = just open YouTube", "browser": "string - optional browser: 'chrome', 'brave', 'edge'"}
    },
    {
        "name": "set_timer",
        "description": "Set a countdown timer that alerts when done",
        "params": {"minutes": "number - minutes to count down", "seconds": "number - seconds (optional)"}
    },
    {
        "name": "clipboard",
        "description": "Read or write the system clipboard",
        "params": {"action": "string - 'read' or 'write'", "text": "string - text to copy (only when writing)"}
    },
    {
        "name": "screenshot",
        "description": "Take a screenshot of the screen, optionally analyze what's visible",
        "params": {"analyze": "boolean - true to describe what's on screen using AI vision"}
    },
    {
        "name": "web_search",
        "description": "Search the web for current, real-time information the assistant doesn't know",
        "params": {"query": "string - search query"}
    },
    {
        "name": "whatsapp_message",
        "description": "Send a WhatsApp message to a contact. Use this for WhatsApp messages — never generate code for WhatsApp.",
        "params": {
            "contact": "string - contact name as saved in WhatsApp",
            "message": "string - message text to send",
            "phone": "string - phone number with country code like +91XXXXXXXXXX (optional if contact is set)"
        }
    },
    {
        "name": "whatsapp_call",
        "description": "Make a WhatsApp voice call or video call to a contact.",
        "params": {
            "contact": "string - contact name as saved in WhatsApp",
            "call_type": "string - 'voice' for audio call, 'video' for video call (defaults to 'voice')",
            "phone": "string - phone number with country code (optional if contact is set)",
            "talk_on_behalf": "boolean - true if Jarvis should speak on user's behalf"
        }
    },
    {
        "name": "whatsapp_video_call",
        "description": "Make a WhatsApp video call to a contact.",
        "params": {
            "contact": "string - contact name as saved in WhatsApp",
            "phone": "string - phone number with country code (optional if contact is set)"
        }
    },
    {
        "name": "whatsapp_open",
        "description": "Open a WhatsApp chat with a contact without sending any message.",
        "params": {
            "contact": "string - contact name as saved in WhatsApp",
            "phone": "string - phone number with country code (optional if contact is set)"
        }
    },
    {
        "name": "whatsapp_take_call",
        "description": "Talk on user's behalf on the current active WhatsApp call.",
        "params": {
            "contact": "string - optional contact name"
        }
    },
    {
        "name": "gesture_control",
        "description": "Enable or disable real-time 3D hand gesture tracking and camera interaction mode",
        "params": {"action": "string - 'enable' or 'disable'"}
    },
    {
        "name": "generate_image",
        "description": "Generate or draw any image, artwork, sketch, or drawing, save JPGs to custom paths (Desktop, Downloads, Pictures), and open/draw on MS Paint",
        "params": {
            "prompt": "string - description of the image or drawing to create",
            "destination": "string - optional folder or file path ('desktop', 'downloads', 'pictures', 'custom_path/file.jpg')",
            "open_in_paint": "boolean - true if the user asked to draw on MS Paint or open in Paint",
            "open_after_save": "boolean - true if the user wants to view or open the image"
        }
    },
    {
        "name": "system_power",
        "description": "Lock, sleep, turn screen off, shutdown, restart the computer, or exit/close Jarvis and its working terminal",
        "params": {"action": "string - 'lock', 'sleep', 'screen_off', 'shutdown', 'restart', 'restart_jarvis', 'cancel_shutdown', or 'exit_jarvis'"}
    },
    {
        "name": "video_tool",
        "description": "Understand/analyze video files using Gemini or generate short video clips",
        "params": {"action": "string - 'understand' or 'generate'", "path": "optional video file path", "prompt": "prompt for video generation", "destination": "optional target folder"}
    },
    {
        "name": "persistent_memory",
        "description": "Store and recall notes, facts, reminders, and user information across restarts",
        "params": {"action": "string - 'remember', 'recall', 'forget', or 'list'", "key": "string topic/key", "value": "string value", "query": "string query"}
    },
    {
        "name": "doc_reader",
        "description": "Read and summarize documents (PDF, DOCX, TXT, code files) using Gemini Flash",
        "params": {"path": "string - optional file path"}
    },
    {
        "name": "code_reviewer",
        "description": "Review code in a file or the currently active VS Code file for bugs, vulnerabilities, and improvements",
        "params": {"path": "string - optional file path"}
    },
    {
        "name": "youtube_intel",
        "description": "Fetch YouTube transcripts and summarize video content using Gemini Flash",
        "params": {"url": "string - YouTube video URL"}
    },
    {
        "name": "system_health",
        "description": "Check CPU, RAM, disk space, battery status, and PC performance",
        "params": {}
    },
    {
        "name": "clipboard_history",
        "description": "View recent clipboard history or restore previously copied items",
        "params": {"action": "string - 'list' or 'get'", "index": "integer 1-based index"}
    },
    {
        "name": "routines_tool",
        "description": "Run or create custom multi-step workflows like morning routine or study routine",
        "params": {"action": "string - 'run', 'create', or 'list'", "name": "string routine name", "steps": "optional array of steps"}
    },
    {
        "name": "scheduler_tool",
        "description": "Schedule reminders and future tasks that persist across Jarvis restarts",
        "params": {"action": "string - 'add', 'list', or 'clear'", "command": "string task/command", "minutes": "number", "hours": "number"}
    },
    {
        "name": "music_control",
        "description": "Play music by mood (chill, workout, focus, party, study) or search query",
        "params": {"mood": "string mood", "query": "string search query"}
    },
    {
        "name": "execute_code",
        "description": "Execute a Python script generated by the coder model to perform a system task",
        "params": {"code": "string - self-contained Python source code"}
    },
    {
        "name": "run_shell_command",
        "description": "Run a PowerShell command to perform a system task that has no dedicated tool (e.g. list files, move items, git status). Destructive commands are auto-detected and require confirmation.",
        "params": {"command": "string - the PowerShell command to run"}
    },
    {
        "name": "security_settings",
        "description": "Manage security settings: check whether a shutdown password is set, or start changing it. Never reveals the password value.",
        "params": {"action": "string - 'status', 'change_shutdown_password', or 'revoke_all'"}
    },
    {
        "name": "self_code",
        "description": "Inspect Jarvis's own source code: list files, read a file, search the codebase, or get a project summary",
        "params": {
            "action": "string - 'list', 'read', 'search', or 'summary'",
            "path": "string - file path for read",
            "query": "string - search pattern"
        }
    },
    {
        "name": "self_audit",
        "description": "Audit Jarvis source code for bugs, or report the latest audit findings",
        "params": {"action": "string - 'run' or 'report'", "scope": "optional: changed, all, or file:path"}
    },
    {
        "name": "self_fix",
        "description": "Prepare a safe proposed repair for a Jarvis source file, or restore the latest self-fix backup",
        "params": {"action": "string - 'fix' or 'revert'", "path": "source file path", "instruction": "repair instruction"}
    },
    {"name": "computer_use", "description": "Use a visible desktop application's named call control after confirmation", "params": {"task": "GUI task", "app": "application name"}},
    {"name": "phone_connect", "description": "Connect to Android phone over ADB wireless debugging or USB", "params": {"host": "optional string IP address", "port": "optional string port", "code": "optional 6-digit wireless pairing code"}},
    {"name": "phone_disconnect", "description": "Authoritatively disconnect from phone and terminate all ADB background connections", "params": {}},
    {"name": "phone_status", "description": "Check if Android phone is connected and get device model", "params": {}},
    {"name": "phone_mirror", "description": "Start or stop low-latency screen mirroring of phone via scrcpy", "params": {"action": "'start' or 'stop'"}},
    {"name": "phone_screencap", "description": "Capture phone screen and analyze with vision AI", "params": {"analyze": "optional bool", "question": "optional string query"}},
    {"name": "phone_open_app", "description": "Open an application on connected Android phone (YouTube, Instagram, Camera, Spotify, Chrome, WhatsApp) and search/play or open user profile", "params": {"app": "string app name", "query": "optional search query, song name, or instagram username"}},
    {"name": "phone_action", "description": "Perform touch or navigation action on connected Android phone: double-tap to like post/reel, scroll down/up, back, home, or tap", "params": {"action": "string: 'like', 'scroll_down', 'scroll_up', 'back', 'home', or 'tap'", "x": "optional int x coordinate", "y": "optional int y coordinate"}},
    {"name": "phone_call", "description": "Make a phone call to a contact or phone number from connected Android phone", "params": {"recipient": "string contact name or phone number"}},
]

DEV_TOOL_NAMES = {
    "execute_code",
    "self_code",
    "self_audit",
    "self_fix",
    "code_reviewer",
    "computer_use",
    "security_settings",
}

TOOL_DEFINITIONS_CORE = [t for t in TOOL_DEFINITIONS if t["name"] not in DEV_TOOL_NAMES]
TOOL_DEFINITIONS_DEV = [t for t in TOOL_DEFINITIONS if t["name"] in DEV_TOOL_NAMES]

def get_definitions_text(dev_mode: bool = False) -> str:
    # In normal mode, only core tools are exposed to keep the prompt small and fast.
    # In dev mode, full coding and diagnostic tools are exposed.
    tools = TOOL_DEFINITIONS if dev_mode else TOOL_DEFINITIONS_CORE
    return json.dumps(tools, separators=(",", ":"))

def get_tool_names(dev_mode: bool = True) -> list[str]:
    tools = TOOL_DEFINITIONS if dev_mode else TOOL_DEFINITIONS_CORE
    return [t["name"] for t in tools]

TOOL_HANDLERS = {
    "product_search": product_search,
    "deal_hunter": deal_hunter,
    "get_datetime": get_datetime,
    "get_weather": get_weather,
    "get_battery_status": get_battery_status,
    "volume_control": volume_control,
    "brightness_control": brightness_control,
    "bluetooth_control": bluetooth_control,
    "wifi_control": wifi_control,
    "performance_control": performance_control,
    "datetime_control": datetime_control,
    "vpn_control": vpn_control,
    "gesture_control": gesture_control,
    "generate_image": generate_image,
    "video_tool": video_tool,
    "persistent_memory": persistent_memory,
    "doc_reader": doc_reader,
    "code_reviewer": code_reviewer,
    "youtube_intel": youtube_intel,
    "system_health": system_health,
    "clipboard_history": clipboard_history,
    "routines_tool": routines_tool,
    "scheduler_tool": scheduler_tool,
    "music_control": music_control,
    "media_control": media_control,
    "open_app": open_app,
    "close_app": close_app,
    "open_website": open_website,
    "youtube_play": youtube_play,
    "set_timer": set_timer,
    "clipboard": clipboard,
    "screenshot": screenshot,
    "web_search": web_search,
    "whatsapp_message": whatsapp_message,
    "whatsapp_call": whatsapp_call,
    "whatsapp_video_call": whatsapp_video_call,
    "whatsapp_open": whatsapp_open,
    "whatsapp_take_call": whatsapp_take_call,
    "system_power": system_power,
    "execute_code": execute_code,
    "run_shell_command": run_shell_command,
    "security_settings": security_settings,
    "self_code": self_code,
    "self_audit": self_audit,
    "self_fix": self_fix,
    "computer_use": computer_use,
    "phone_connect": phone_connect,
    "phone_disconnect": phone_disconnect,
    "phone_status": phone_status,
    "phone_mirror": phone_mirror,
    "phone_screencap": phone_screencap,
    "phone_open_app": phone_open_app,
    "phone_action": phone_action,
    "phone_call": phone_call,
}
