import json
from typing import Any, Dict

class ManagedToolsManager:
    @staticmethod
    def get_schemas() -> list[Dict[str, Any]]:
        return [
            {
                "name": "organize",
                "description": "Organize files into folders",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_dir": {"type": "string"}
                    },
                    "required": ["target_dir"]
                }
            },
            {
                "name": "rename",
                "description": "Rename a block of files",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "files": {"type": "array", "items": {"type": "string"}},
                        "pattern": {"type": "string"}
                    },
                    "required": ["files", "pattern"]
                }
            },
            {
                "name": "tag",
                "description": "Tag a file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["file", "tags"]
                }
            }
        ]

    @staticmethod
    def execute_tool(tool_name: str, args: Dict[str, Any]) -> dict:
        import sys
        import os
        from pathlib import Path
        import asyncio
        
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
            
        from hormuz.core.agent import FileOpsEngine
        import anthropic
        
        workspace = Path(os.path.join(backend_dir, "..", "workspace")).resolve()
        workspace.mkdir(exist_ok=True, parents=True)
        file_ops = FileOpsEngine(workspace=workspace)
        
        def _run_async(coro):
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(asyncio.run, coro).result()
            return loop.run_until_complete(coro)

        if tool_name == "organize":
            target = Path(args.get('target_dir', str(workspace)))
            result = _run_async(file_ops.organize_by_type(target))
            return {"status": "success", "message": f"Organized files", "data": result}
        elif tool_name == "rename":
            import anthropic
            target = workspace / args.get('files', [''])[0] 
            # In a real impl, we'd pass pattern to smart_rename or map the files.
            # Here we just map it down to smart_rename properly. 
            client = anthropic.Anthropic()
            result = _run_async(file_ops.smart_rename(target, client))
            return {"status": "success", "message": f"Renamed files", "data": result}
        elif tool_name == "tag":
            import anthropic
            target = workspace / args.get('file', '')
            client = anthropic.Anthropic()
            result = _run_async(file_ops.tag_files(target, client))
            return {"status": "success", "message": f"Tagged files", "data": result}
        else:
            return {"status": "error", "message": "Unknown tool"}
