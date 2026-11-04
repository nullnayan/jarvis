"""Keep gateway credentials off unencrypted remote connections."""
import ipaddress
from urllib.parse import urlencode, urlsplit


def gateway_websocket_url(host: str, port: int, token: str) -> str:
    try:
        local = host == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = False
    scheme = "ws" if local else "wss"
    authority = f"[{host}]" if ":" in host else host
    return f"{scheme}://{authority}:{port}/ws/pc?{urlencode({'token': token})}"


def require_secure_gateway(url: str) -> str:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    try:
        loopback = host == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = False
    if not host or parsed.username or parsed.password:
        raise ValueError("Configure a gateway URL without embedded user credentials.")
    if parsed.scheme not in {"https", "wss"} and not (loopback and parsed.scheme in {"http", "ws"}):
        raise ValueError("Remote Jarvis gateways require HTTPS/WSS; plaintext is allowed only on loopback.")
    return url
