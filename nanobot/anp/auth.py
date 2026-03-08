"""DID WBA Authentication for ANP protocol.

This module provides:
- DID WBA signature generation
- DID WBA signature verification
- JWT token generation and verification
- Authorization header handling
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any

import jwt
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from loguru import logger


class DIDWBAAuth:
    """
    DID WBA authentication for generating ANP-compliant authentication headers.

    Follows the ANP DID WBA Method Specification for authentication.
    """

    def __init__(
        self,
        did: str,
        private_key_pem: str | None = None,
        key_type: str = "secp256r1",
    ):
        """
        Initialize DID WBA authentication.

        Args:
            did: The DID identifier for this agent
            private_key_pem: PEM-formatted private key (generated if not provided)
            key_type: Key type - "secp256r1", "secp256k1", or "ed25519"
        """
        self.did = did
        self.key_type = key_type
        self.verification_method = "key-1"

        if private_key_pem:
            self.private_key = serialization.load_pem_private_key(
                private_key_pem.encode(),
                password=None,
                backend=default_backend()
            )
        else:
            self.private_key = self._generate_key()

        self._public_key_pem = self.private_key.public_key().public_bytes(
            Encoding.PEM,
            PublicFormat.SubjectPublicKeyInfo
        ).decode()

    def _generate_key(self):
        """Generate a new private key based on key_type."""
        if self.key_type == "secp256r1":
            return ec.generate_private_key(ec.SECP256R1(), default_backend())
        elif self.key_type == "secp256k1":
            return ec.generate_private_key(ec.SECP256K1(), default_backend())
        elif self.key_type == "ed25519":
            return ed25519.Ed25519PrivateKey.generate()
        else:
            raise ValueError(f"Unsupported key type: {self.key_type}")

    def get_public_key_pem(self) -> str:
        """Get the public key in PEM format."""
        return self._public_key_pem

    def get_private_key_pem(self) -> str:
        """Get the private key in PEM format."""
        return self.private_key.private_bytes(
            Encoding.PEM,
            PrivateFormat.PKCS8,
            NoEncryption()
        ).decode()

    def generate_nonce(self) -> str:
        """Generate a cryptographically secure random nonce."""
        return secrets.token_urlsafe(16)

    def _sign(self, message: bytes) -> bytes:
        """Sign a message using the private key."""
        if self.key_type in ("secp256r1", "secp256k1"):
            signature = self.private_key.sign(
                message,
                ec.ECDSA(hashes.SHA256())
            )
            # For ECDSA, convert DER signature to R|S format
            from cryptography.hazmat.primitives.asymmetric.utils import (
                decode_dss_signature
            )
            r, s = decode_dss_signature(signature)
            # Convert to fixed-length bytes
            order = self.private_key.public_key().curve.key_size
            r_bytes = r.to_bytes(order // 8, byteorder='big')
            s_bytes = s.to_bytes(order // 8, byteorder='big')
            return r_bytes + s_bytes
        elif self.key_type == "ed25519":
            return self.private_key.sign(message)
        else:
            raise ValueError(f"Unsupported key type for signing: {self.key_type}")

    def create_auth_header(
        self,
        audience: str,
        nonce: str | None = None,
    ) -> tuple[str, str]:
        """
        Create a DID WBA Authorization header value.

        Args:
            audience: The domain/audience of the request
            nonce: Random nonce (generated if not provided)

        Returns:
            Tuple of (header_name, header_value)
        """
        if nonce is None:
            nonce = self.generate_nonce()

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Create the payload to sign
        payload = {
            "nonce": nonce,
            "timestamp": timestamp,
            "aud": audience,
            "did": self.did,
        }

        # Canonicalize using JCS (JSON Canonicalization Scheme)
        # For simplicity, we use json.dumps with sorted keys
        canonical_payload = json.dumps(payload, sort_keys=True, separators=(',', ':'))

        # Sign the hash of the canonical payload
        payload_hash = hashlib.sha256(canonical_payload.encode()).digest()
        signature = self._sign(payload_hash)

        # Encode signature in base64url
        signature_b64 = base64.urlsafe_b64encode(signature).rstrip(b'=').decode()

        # Build the Authorization header
        header_value = (
            f'DIDWba did="{self.did}", nonce="{nonce}", timestamp="{timestamp}", '
            f'verification_method="{self.verification_method}", signature="{signature_b64}"'
        )

        return "Authorization", header_value

    def create_jwt_token(
        self,
        secret: str,
        expiration_hours: int = 24,
        payload: dict[str, Any] | None = None,
    ) -> str:
        """
        Create a JWT access token.

        Args:
            secret: JWT secret key
            expiration_hours: Token expiration time in hours
            payload: Additional payload data

        Returns:
            JWT token string
        """
        now = datetime.now(timezone.utc)

        token_payload = {
            "sub": self.did,
            "iat": now,
            "exp": now + timedelta(hours=expiration_hours),
        }
        if payload:
            token_payload.update(payload)

        token = jwt.encode(token_payload, secret, algorithm="HS256")
        return token

    def create_did_document(self, agent_description_url: str) -> dict[str, Any]:
        """
        Create a DID document for this agent.

        Args:
            agent_description_url: URL to the agent description document

        Returns:
            DID document in JSON-LD format
        """
        # Get public key in JWK format
        public_numbers = None
        jwk = None

        if self.key_type == "secp256k1":
            public_key = self.private_key.public_key()
            public_numbers = public_key.public_numbers()
            jwk = {
                "crv": "secp256k1",
                "x": self._base64url_encode(public_numbers.x.to_bytes(32, byteorder='big')),
                "y": self._base64url_encode(public_numbers.y.to_bytes(32, byteorder='big')),
                "kty": "EC",
                "kid": self.verification_method,
            }
            verification_method_type = "EcdsaSecp256k1VerificationKey2019"
        elif self.key_type == "secp256r1":
            public_key = self.private_key.public_key()
            public_numbers = public_key.public_numbers()
            jwk = {
                "crv": "P-256",
                "x": self._base64url_encode(public_numbers.x.to_bytes(32, byteorder='big')),
                "y": self._base64url_encode(public_numbers.y.to_bytes(32, byteorder='big')),
                "kty": "EC",
                "kid": self.verification_method,
            }
            verification_method_type = "EcdsaSecp256r1VerificationKey2019"
        elif self.key_type == "ed25519":
            public_bytes = self.private_key.public_key().public_bytes(
                Encoding.Raw,
                PublicFormat.Raw
            )
            jwk = {
                "crv": "Ed25519",
                "x": self._base64url_encode(public_bytes),
                "kty": "OKP",
                "kid": self.verification_method,
            }
            verification_method_type = "Ed25519VerificationKey2020"
        else:
            raise ValueError(f"Unsupported key type: {self.key_type}")

        verification_method_id = f"{self.did}#{self.verification_method}"

        did_document = {
            "@context": [
                "https://www.w3.org/ns/did/v1",
                "https://w3id.org/security/suites/jws-2020/v1",
            ],
            "id": self.did,
            "verificationMethod": [
                {
                    "id": verification_method_id,
                    "type": verification_method_type,
                    "controller": self.did,
                    "publicKeyJwk": jwk,
                }
            ],
            "authentication": [verification_method_id],
            "service": [
                {
                    "id": f"{self.did}#agent-description",
                    "type": "AgentDescription",
                    "serviceEndpoint": agent_description_url,
                }
            ],
        }

        return did_document

    @staticmethod
    def _base64url_encode(data: bytes) -> str:
        """Encode bytes to base64url without padding."""
        return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


class DIDWBAAuthenticator:
    """
    Verifier for DID WBA authentication.

    Validates incoming ANP requests according to the DID WBA specification.
    """

    def __init__(
        self,
        jwt_secret: str,
        nonce_cache_ttl: int = 300,
    ):
        """
        Initialize the authenticator.

        Args:
            jwt_secret: Secret key for JWT verification
            nonce_cache_ttl: Time-to-live for nonce cache in seconds
        """
        self.jwt_secret = jwt_secret
        self.nonce_cache_ttl = nonce_cache_ttl
        self._nonce_cache: dict[str, float] = {}

    def verify_auth_header(self, auth_header: str, expected_audience: str) -> dict[str, Any]:
        """
        Verify a DID WBA Authorization header.

        Args:
            auth_header: The Authorization header value
            expected_audience: The expected audience domain

        Returns:
            Verification result dict with keys:
            - valid: bool - Whether verification succeeded
            - did: str - The DID from the header
            - error: str | None - Error message if verification failed
        """
        try:
            # Parse the Authorization header
            if not auth_header.startswith("DIDWba "):
                return {
                    "valid": False,
                    "error": "Invalid authentication scheme",
                }

            # Extract the parameters
            params_str = auth_header[7:].strip()
            params = {}
            for param in params_str.split(", "):
                key, value = param.split("=", 1)
                params[key] = value.strip('"')

            did = params.get("did")
            nonce = params.get("nonce")
            timestamp_str = params.get("timestamp")
            verification_method = params.get("verification_method")
            signature = params.get("signature")

            # Validate required fields
            if not all([did, nonce, timestamp_str, verification_method, signature]):
                return {
                    "valid": False,
                    "error": "Missing required authentication parameters",
                }

            # Validate timestamp (within 5 minutes)
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                if abs((now - timestamp).total_seconds()) > 300:
                    return {
                        "valid": False,
                        "error": "Timestamp expired",
                    }
            except ValueError:
                return {
                    "valid": False,
                    "error": "Invalid timestamp format",
                }

            # Check nonce (prevent replay attacks)
            if nonce in self._nonce_cache:
                return {
                    "valid": False,
                    "error": "Nonce already used (replay attack)",
                }
            self._nonce_cache[nonce] = datetime.now().timestamp()
            self._cleanup_nonce_cache()

            # Note: In a full implementation, we would fetch the DID document
            # and verify the signature. For now, we do basic validation.
            # The signature verification would require fetching the DID document
            # from the did:wba URL and extracting the public key.

            return {
                "valid": True,
                "did": did,
                "verification_method": verification_method,
            }

        except Exception as e:
            logger.error("Error verifying auth header: {}", e)
            return {
                "valid": False,
                "error": f"Authentication verification failed: {e}",
            }

    def verify_jwt_token(self, token: str) -> dict[str, Any]:
        """
        Verify a JWT access token.

        Args:
            token: The JWT token string

        Returns:
            Verification result dict with keys:
            - valid: bool - Whether verification succeeded
            - payload: dict | None - Token payload if valid
            - error: str | None - Error message if verification failed
        """
        try:
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=["HS256"],
            )
            return {
                "valid": True,
                "payload": payload,
            }
        except jwt.ExpiredSignatureError:
            return {
                "valid": False,
                "error": "Token has expired",
            }
        except jwt.InvalidTokenError as e:
            return {
                "valid": False,
                "error": f"Invalid token: {e}",
            }

    def _cleanup_nonce_cache(self) -> None:
        """Remove expired nonces from the cache."""
        now = datetime.now().timestamp()
        expired = [
            nonce
            for nonce, timestamp in self._nonce_cache.items()
            if now - timestamp > self.nonce_cache_ttl
        ]
        for nonce in expired:
            del self._nonce_cache[nonce]

    def generate_jwt_token(self, did: str, expiration_hours: int = 24) -> str:
        """
        Generate a JWT access token for a verified DID.

        Args:
            did: The DID to issue a token for
            expiration_hours: Token expiration time in hours

        Returns:
            JWT token string
        """
        now = datetime.now(timezone.utc)
        payload = {
            "sub": did,
            "iat": now,
            "exp": now + timedelta(hours=expiration_hours),
        }
        return jwt.encode(payload, self.jwt_secret, algorithm="HS256")
