"""
Teste funcional do Agente Hormuz — sem LLM, sem input interativo.
Valida: init, submit, store, sync, status, task result via hormuz_bridge.
"""
import sys, os, asyncio
sys.path.insert(0, 'backend')
os.environ['PYTHONIOENCODING'] = 'utf-8'

from pathlib import Path
from hormuz.core.agent import HormuzAgent, HormuzTask, TaskStatus, TaskPriority, HORMUZ_HOME

print('=== TESTE AGENTE HORMUZ ===')
print()

# 1. Instanciar agente com sandbox = workspace
sandbox = Path(r'D:\Strait of Hormuz\Strait of Hormuz\workspace')
sandbox.mkdir(exist_ok=True)

agent = HormuzAgent(sandbox_root=sandbox)
print('1. HormuzAgent inicializado OK')
print('   device:', agent.status()['device'])
print('   hostname:', agent.status()['hostname'])
print('   HORMUZ_HOME:', HORMUZ_HOME)

# 2. Submeter uma tarefa generic (sem LLM)
task = HormuzTask(
    title='Teste Core — generic handler',
    task_type='generic',
    priority=TaskPriority.HIGH,
    description='Tarefa de teste do pipeline Core',
    params={'test': True}
)
agent.submit_task(task)
print()
print('2. Task submetida:', task.task_id, '|', task.status.value)

# 3. Verificar no store
stored = agent.store.get(task.task_id)
assert stored is not None
assert stored.status == TaskStatus.PENDING
print('3. Task no store: OK | status:', stored.status.value)

# 4. Executar handler generic diretamente (simula worker sem thread)
async def run_generic():
    from anthropic_stub import Anthropic
    client = Anthropic()   # sem API key real -- não vai fazer chamada
    result = await agent._handle_generic(task, client)
    return result

result = asyncio.run(run_generic())
print('4. Handler generic executado:', result)

# 5. Sync push (escreve sync.json)
agent.sync.push(agent.store, agent.state)
sync_file = HORMUZ_HOME / 'sync.json'
assert sync_file.exists()
print('5. Sync push OK:', sync_file)

# 6. Status final
s = agent.status()
print()
print('6. Status final:')
for k, v in s.items():
    print(f'   {k}: {v}')

# 7. Cancel test
task2 = HormuzTask(title='Tarefa para cancelar', task_type='generic')
agent.submit_task(task2)
cancelled = agent.store.cancel(task2.task_id)
assert cancelled
assert agent.store.get(task2.task_id).status == TaskStatus.CANCELLED
print()
print('7. Cancel task:', task2.task_id, '-> CANCELLED OK')

# 8. Module 9 sanitization via bridge
from module9_sanitizer import SubAgentResult, sanitize_sub_agent_result, SanitizationStatus
sub = SubAgentResult('hormuz.generic', task.task_id, task.description, result, None)
san = sanitize_sub_agent_result(sub)
assert san.status == SanitizationStatus.CLEAN
print()
print('8. Resultado passado pelo Module 9:', san.status.value)

print()
print('=== TODOS OS TESTES PASSARAM ===')
