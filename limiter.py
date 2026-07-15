from slowapi import Limiter
from starlette.requests import Request

def get_real_ip(request: Request) -> str:
    # Check X-Forwarded-For header first (used by reverse proxies like Render)
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # Take the first IP in the list, which is the original client IP
        return forwarded_for.split(",")[0].strip()
    
    # Fallback to standard request.client.host
    return request.client.host if request.client else "127.0.0.1"

limiter = Limiter(key_func=get_real_ip, headers_enabled=False, default_limits=["100/minute"])
