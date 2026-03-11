# UNUSED (commented out)
#
# This module supported the (now disabled) Lobby page by redirecting premature POSTs.
# Current production flow has no Lobby; grouping happens only at BatchWaitForGroup.
#
# from starlette.responses import RedirectResponse
#
# class LobbyWaitRequired(Exception):
#     \"\"\"Raised when a Lobby POST is submitted before the participant is allowed to leave.\"\"\"
#
# async def lobby_wait_handler(request, exc):
#     return RedirectResponse(url=request.url.path, status_code=303)
