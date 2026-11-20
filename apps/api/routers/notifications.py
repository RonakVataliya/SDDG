"""The notifications bell: list, unread count, mark read. Other features create notifications with
core.notifications.notify(); nothing here is project-scoped, a user only ever sees their own."""
from fastapi import APIRouter, Depends, HTTPException, Response

from core import notifications
from core.auth import User, get_current_user
from routers.integrated import NOT_FOUND

router = APIRouter()


@router.get("/notifications")
def list_notifications(user: User = Depends(get_current_user)):
    """The newest 50 notifications, newest first, with the unread count for the bell's red badge."""
    return {"unread_count": notifications.unread_count(user), "items": notifications.list_notifications(user)}


@router.get("/notifications/unread-count")
def unread_count(user: User = Depends(get_current_user)):
    """Just the number, cheap enough for the bell to poll."""
    return {"count": notifications.unread_count(user)}


@router.post("/notifications/read-all", status_code=204)
def read_all(user: User = Depends(get_current_user)):
    notifications.mark_all_read(user.id)
    return Response(status_code=204)


@router.post("/notifications/{notification_id}/read", status_code=204)
def read_one(notification_id: str, user: User = Depends(get_current_user)):
    if not notifications.mark_read(user.id, notification_id):
        raise HTTPException(404, NOT_FOUND)
    return Response(status_code=204)
