import json

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from chat_graph import run_chat
from database import get_db
from models import ConversationMessage, Project, ProjectImage

router = APIRouter(prefix="/api/projects", tags=["chat"])


class SendMessageRequest(BaseModel):
    content: str


def _user_id(x_user_id: str = Header(default="anonymous")) -> str:
    return x_user_id


def _get_project_or_404(project_id: str, user_id: str, db: Session) -> Project:
    p = db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


@router.post("/{project_id}/chat/message")
def send_message(
    project_id: str,
    req: SendMessageRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(_user_id),
):
    p = _get_project_or_404(project_id, user_id, db)

    # Persist user message
    user_msg = ConversationMessage(project_id=project_id, role="user", content=req.content)
    db.add(user_msg)
    db.commit()

    # Build full history including new user message
    all_messages = (
        db.query(ConversationMessage)
        .filter_by(project_id=project_id)
        .order_by(ConversationMessage.created_at)
        .all()
    )
    history = [{"role": m.role, "content": m.content} for m in all_messages]
    project_lids = [img.lid for img in p.images]

    reply_text, image_results = run_chat(project_lids, history)

    img_json = json.dumps(image_results) if image_results else None
    assistant_msg = ConversationMessage(project_id=project_id, role="assistant", content=reply_text, image_results=img_json)
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)

    return {"role": "assistant", "content": reply_text, "image_results": image_results, "created_at": assistant_msg.created_at.isoformat()}


@router.get("/{project_id}/chat/history")
def get_history(
    project_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(_user_id),
):
    _get_project_or_404(project_id, user_id, db)
    messages = (
        db.query(ConversationMessage)
        .filter_by(project_id=project_id)
        .order_by(ConversationMessage.created_at)
        .all()
    )
    return [
        {
            "role": m.role,
            "content": m.content,
            "image_results": json.loads(m.image_results) if m.image_results else None,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]


@router.delete("/{project_id}/chat/history", status_code=204)
def clear_history(
    project_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(_user_id),
):
    _get_project_or_404(project_id, user_id, db)
    db.query(ConversationMessage).filter_by(project_id=project_id).delete()
    db.commit()
