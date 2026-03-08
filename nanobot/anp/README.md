# ANP Implementation for nanobot

This document describes the ANP (Agent Network Protocol) implementation for nanobot.

## Overview

Nanobot has been enhanced to support the ANP protocol, enabling it to:

1. **Act as Agent A** (User Representative) in the ANP network
2. **Receive ANP requests** from other agents (server mode)
3. **Send ANP requests** to other agents (client mode)
4. **Authenticate using DID WBA** (Decentralized Identity)

## Architecture

### Components

```
nanobot/anp/
├── __init__.py           # Package initialization
├── agent_registry.py     # Agent registry (JSON-LD format)
├── auth.py              # DID WBA authentication
├── client.py            # ANP client (send requests)
├── server.py            # ANP server (receive requests)
└── test_scenario.py     # Test scenario simulation
```

### Integration Points

- **Agent Loop** (`nanobot/agent/loop.py`): Registers ANP tools and starts ANP server
- **Config Schema** (`nanobot/config/schema.py`): Adds ANP configuration options
- **Skills** (`nanobot/skills/anp/`): ANP skill for LLM integration

## Configuration

Add ANP configuration to `~/.nanobot/config.json`:

```json
{
  "anp": {
    "enabled": true,
    "host": "0.0.0.0",
    "port": 8080,
    "jwt_secret": "your-secret-key",
    "auth_enabled": true,
    "did": "did:wba:nanobot.local:agent:user-representative"
  }
}
```

## Agent Registry

The agent registry is stored at `~/.nanobot/agents.json` in JSON-LD format.

### Default Agents

1. **nanobot** (Agent A)
   - Role: User Representative
   - DID: `did:wba:nanobot.local:agent:user-representative`
   - Capabilities: Human-in-the-loop authorization, verification code provision

2. **smart-home-hub** (Agent B)
   - Role: Security Supervisor
   - DID: `did:wba:smarthome.local:agent:hub`
   - Capabilities: Security status monitoring, security upgrade verification

3. **cloud-storage** (Agent C)
   - Role: Data Storage Provider
   - DID: `did:wba:cloudstorage.local:agent:storage`
   - Capabilities: Secure data storage, log management

## Usage

### For Users

When ANP is enabled, you can interact with other agents through natural language:

```
User: "Check security status"
Nanobot: [Calls Smart Home Hub's getSecurityStatus method]

User: "List available agents"
Nanobot: [Shows all registered ANP agents]
```

### For Developers

#### Using ANP Client

```python
from nanobot.anp.client import ANPClient
from nanobot.anp.auth import DIDWBAAuth

# Initialize
auth = DIDWBAAuth(did="did:wba:nanobot.local:agent:user-representative")
client = ANPClient(auth=auth)

# Call remote agent
result = await client.call(
    agent_name="smart-home-hub",
    method="getSecurityStatus",
    params={}
)
```

#### Using ANP Server

The ANP server automatically starts when `anp.enabled` is true. It provides:

- `GET /.well-known/did.json` - DID document
- `GET /ad.json` - Agent description
- `POST /anp/rpc` - JSON-RPC 2.0 endpoint
- `GET /health` - Health check

## DID WBA Authentication

### Authentication Flow

1. Client creates DID WBA auth header with:
   - DID identifier
   - Nonce (random)
   - Timestamp
   - Signature (using private key)

2. Server verifies:
   - Timestamp freshness (within 5 minutes)
   - Nonce uniqueness (replay prevention)
   - Signature validity (using public key from DID document)

3. On success, server issues JWT token for subsequent requests

### Key Management

- Private keys stored at `~/.nanobot/anp_private_key.pem`
- Keys generated automatically on first use
- Use secp256r1 (P-256) curve for signatures

## Test Scenario

Run the test scenario:

```bash
python -m nanobot.anp.test_scenario
```

This simulates the security verification flow described in the requirements.

## Security Considerations

1. **Replay Protection**: Nonce cache prevents replay attacks
2. **Timestamp Validation**: Requests expire after 5 minutes
3. **DID Verification**: DID documents fetched from HTTPS endpoints
4. **Human-in-the-Loop**: Sensitive operations require user approval

## Future Enhancements

1. **Dynamic Agent Discovery**: Fetch agent descriptions from remote URLs
2. **E2E Encryption**: Implement end-to-end encryption using X25519
3. **Protocol Negotiation**: Support ANP meta-protocol negotiation
4. **Multi-DID Support**: Multiple DIDs for different contexts

## References

- [ANP Technical Specifications](https://github.com/agent-network-protocol/AgentNetworkProtocol)
- [AgentConnect SDK](https://github.com/agent-network-protocol/AgentConnect)
- [DID WBA Method Specification](https://github.com/agent-network-protocol/AgentNetworkProtocol/blob/main/03-did-wba-method-design-specification.md)
- [ANP Agent Description Protocol](https://github.com/agent-network-protocol/AgentNetworkProtocol/blob/main/07-anp-agent-description-protocol-specification.md)
