# Custom exception and ASGI handler so Lobby POST when can_leave_lobby is False
# returns a redirect (303) instead of 500. Registered in settings.py.
from starlette.responses import RedirectResponse


class LobbyWaitRequired(Exception):
    """Raised when a Lobby POST is submitted before the participant is allowed to leave."""


async def lobby_wait_handler(request, exc):
    return RedirectResponse(url=request.url.path, status_code=303)
