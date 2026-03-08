"""Test File X agent discovery and ANP protocol compliance."""

import sys
import json
sys.path.insert(0, '/public/gongxiayu/study/nanobot')

from nanobot.anp.agent_registry import AgentRegistry

print("=" * 70)
print("任务1验证：智能体描述文档 (File X)")
print("=" * 70)

registry = AgentRegistry()

# Check 1: File exists
import os
registry_path = os.path.expanduser("~/.nanobot/agents.json")
print(f"\n✓ 文件X路径: {registry_path}")
print(f"✓ 文件存在: {os.path.exists(registry_path)}")

# Check 2: JSON-LD format
with open(registry_path, 'r') as f:
    data = json.load(f)

print(f"\n✓ JSON格式验证通过")

# Check 3: Required fields per ANP spec
print("\n--- ANP Agent Description 协议规范验证 ---\n")

for agent_name, agent in data.get("agents", {}).items():
    print(f"Agent: {agent_name}")

    # 1. DID
    did = agent.get("did")
    if did and did.startswith("did:wba:"):
        print(f"  ✅ DID: {did}")
    else:
        print(f"  ❌ DID缺失或格式错误")

    # 2. JSON-LD context
    context = agent.get("@context")
    if context and "w3.org/ns/did/v1" in context:
        print(f"  ✅ JSON-LD @context: {context}")
    else:
        print(f"  ❌ JSON-LD @context 缺失")

    # 3. Protocol type and version
    if agent.get("protocolType") == "ANP":
        print(f"  ✅ protocolType: ANP")
    else:
        print(f"  ❌ protocolType 错误")

    if agent.get("protocolVersion") == "1.0.0":
        print(f"  ✅ protocolVersion: 1.0.0")
    else:
        print(f"  ❌ protocolVersion 错误")

    # 4. Interfaces (Natural Language + OpenRPC)
    interfaces = agent.get("interfaces", [])
    has_nl = any(i.get("type") == "NaturalLanguageInterface" for i in interfaces)
    has_openrpc = any(i.get("protocol") == "openrpc" for i in interfaces)

    print(f"  {'✅' if has_nl else '❌'} NaturalLanguageInterface: {has_nl}")
    print(f"  {'✅' if has_openrpc else '❌'} OpenRPC interface: {has_openrpc}")

    for iface in interfaces:
        if iface.get("protocol") == "openrpc":
            print(f"      - URL: {iface.get('url')}")

    # 5. Security definitions
    if "securityDefinitions" in agent:
        print(f"  ✅ securityDefinitions: {agent['securityDefinitions']}")
    else:
        print(f"  ❌ securityDefinitions 缺失")

    if "security" in agent:
        print(f"  ✅ security: {agent['security']}")
    else:
        print(f"  ❌ security 字段缺失")

    # 6. Capabilities
    capabilities = agent.get("capabilities", [])
    print(f"  ℹ️  Capabilities: {', '.join(capabilities)}")

    print()

# Check 4: Dynamic discovery - any ANP agent can search
print("--- 动态发现测试 ---\n")

# Scenario: User asks "Check security status"
# LLM should be able to find smart-home-hub via File X
test_searches = [
    ("security", "Security Supervisor"),
    ("storage", "Data Storage Provider"),
    ("authorization", "User Representative"),
]

# Test capability-based search (partial match)
print("能力搜索测试 (部分匹配):")
for keyword, expected_role in test_searches:
    found = []
    for name, agent in data.get("agents", {}).items():
        capabilities = agent.get("capabilities", [])
        role = agent.get("role", "")
        # Search in capabilities
        if any(keyword.lower() in cap.lower() for cap in capabilities):
            found.append((name, role))
        # Also search in role
        elif keyword.lower() in role.lower():
            found.append((name, role))

    print(f"  '{keyword}' -> {found}")

print()
print("=" * 70)
print("✅ 任务1 核验完成")
print("=" * 70)
