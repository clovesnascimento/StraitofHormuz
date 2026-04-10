import sys, os
sys.path.insert(0, 'backend')
os.environ['PYTHONIOENCODING'] = 'utf-8'

from hormuz.core.agent import HormuzTask, TaskStatus, TaskPriority, HORMUZ_HOME
print('agent.py import OK')

import hormuz_bridge
print('hormuz_bridge OK -- routes:', len(hormuz_bridge.hormuz_routes))

from pathlib import Path
xml = Path.home() / '.hormuz' / 'hormuz_task.xml'
print('Task XML exists:', xml.exists())

from module9_sanitizer import sanitize_sub_agent_result
from module10_approval import authorize_operation, ApprovalResult
print('Module 9 + 10: OK')

print('ALL SYSTEMS GREEN')
