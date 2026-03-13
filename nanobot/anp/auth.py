"""DID WBA authentication management using ANP SDK."""

import json
import logging
from pathlib import Path

from anp.authentication import create_did_wba_document, DIDWbaAuthHeader

logger = logging.getLogger(__name__)


class DIDManager:
    """Manage DID document and keys for this agent."""

    def __init__(self, did_dir: Path, hostname: str, path_segments: list[str]):
        """Initialize DID manager.

        Args:
            did_dir: Directory to store DID document and keys
            hostname: Hostname for DID (e.g., "home.local")
            path_segments: Path segments for DID (e.g., ["security-manager"])
        """
        self.did_dir = Path(did_dir).expanduser()
        self.hostname = hostname
        self.path_segments = path_segments
        self.did_doc_path = self.did_dir / "did.json"
        self.private_key_path = self.did_dir / "key-1_private.pem"

    def ensure_did(self) -> str:
        """Ensure DID document and keys exist, create if not. Returns DID string."""
        self.did_dir.mkdir(parents=True, exist_ok=True)

        if self.did_doc_path.exists() and self.private_key_path.exists():
            with open(self.did_doc_path, "r") as f:
                doc = json.load(f)
            return doc.get("id", "")

        # Generate new DID document and keys
        did_document, keys = create_did_wba_document(
            hostname=self.hostname,
            path_segments=self.path_segments,
        )

        # Save DID document
        with open(self.did_doc_path, "w") as f:
            json.dump(did_document, f, indent=2)

        # Save keys
        for fragment, (private_bytes, public_bytes) in keys.items():
            with open(self.did_dir / f"{fragment}_private.pem", "wb") as f:
                f.write(private_bytes)
            with open(self.did_dir / f"{fragment}_public.pem", "wb") as f:
                f.write(public_bytes)

        logger.info("Created DID: %s", did_document["id"])
        return did_document["id"]

    def get_auth_header(self) -> DIDWbaAuthHeader:
        """Get DID WBA auth header for client requests."""
        return DIDWbaAuthHeader(
            did_document_path=str(self.did_doc_path),
            private_key_path=str(self.private_key_path),
        )
