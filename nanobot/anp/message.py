"""ANP message format definition."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ANPMessage:
    """Unified message format for ANP protocol."""

    sender_did: str  # Sender DID (user: "user:feishu:ou_xxx", agent: "did:wba:...")
    receiver_did: str  # Receiver DID
    content: str  # Message content
    message_type: str  # "user_message" | "agent_request" | "agent_response"
    metadata: dict[str, Any] = field(default_factory=dict)  # Extended fields

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "sender_did": self.sender_did,
            "receiver_did": self.receiver_did,
            "content": self.content,
            "message_type": self.message_type,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ANPMessage":
        """Create from dictionary."""
        return cls(
            sender_did=data["sender_did"],
            receiver_did=data["receiver_did"],
            content=data["content"],
            message_type=data["message_type"],
            metadata=data.get("metadata", {}),
        )
