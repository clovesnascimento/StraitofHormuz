import asyncio
import json
from managed_agents import HormuzManagedClient
from managed_tools import ManagedToolsManager

def test_tool_schemas():
    schemas = ManagedToolsManager.get_schemas()
    assert len(schemas) == 3
    names = [s["name"] for s in schemas]
    assert "organize" in names
    assert "rename" in names
    assert "tag" in names
    print("Tool schemas validation passed.")

async def test_client():
    client = HormuzManagedClient(api_key="TEST")
    print(f"Client endpoint: {client.endpoint}")
    assert "deepseek" in client.endpoint or "anthropic" in client.endpoint
    print("Client initialized validation passed.")

if __name__ == "__main__":
    test_tool_schemas()
    asyncio.run(test_client())
    print("All tests passed.")
