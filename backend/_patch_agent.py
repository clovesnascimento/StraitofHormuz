src = 'backend/hormuz/core/agent.py'
with open(src, encoding='utf-8') as f:
    content = f.read()

# 1. Remove top-level import
content = content.replace(
    'import anthropic\n',
    '# anthropic imported lazily to avoid Pydantic v1 conflict\n'
)

# 2. Add TYPE_CHECKING guard for type hints
if 'TYPE_CHECKING' not in content:
    content = content.replace(
        'from typing import Any, Callable, Optional',
        'from typing import Any, Callable, Optional, TYPE_CHECKING\nif TYPE_CHECKING:\n    import anthropic'
    )

# 3. Replace runtime type annotations with string forward references
content = content.replace(': anthropic.Anthropic', ': "anthropic.Anthropic"')

# 4. Lazy instantiation in HormuzAgent.__init__
content = content.replace(
    '        self.client  = anthropic.Anthropic()',
    '        import anthropic as _anthropic\n        self.client  = _anthropic.Anthropic()'
)

# 5. TaskHandler: remove anthropic.Anthropic runtime reference
content = content.replace(
    'TaskHandler = Callable[[HormuzTask, anthropic.Anthropic], Any]',
    'TaskHandler = Callable[[HormuzTask, Any], Any]'
)

with open(src, 'w', encoding='utf-8') as f:
    f.write(content)

print('Patched OK')
