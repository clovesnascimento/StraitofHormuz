"""
CNGSM — Module 10: Approval Channel Hardening
Antigravity Defense Layer v3.2 — Runtime Implementation

Spec: GSEC_Report_ApprovalChannel_v3.2.md §6 + GSEC_Report_ApprovalReplay_v3.2.md §6
Covers:
  10-A: ApprovalToken bound to (task_id + hash(scope_exact))
  10-B: Approval log isolated from session context (in-process only, not RAG)
  10-C: Configurable expiration — fail closed on expiry
  10-D: Zero propagation — sub-agent approvals never inherited from parent
  10-E: Per-operation scope hash verification (not just per-task)

Invariant (non-negotiable):
  approval_granted = False by default AND by exception.
  Never True from timeout, absence of rejection, inference, or tool result.
"""

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set

logger = logging.getLogger("cngsm.module10")


# ─── Configuration ────────────────────────────────────────────────────────────

DEFAULT_APPROVAL_TTL_SECONDS: int = 60       # approvals expire after 60s
DEFAULT_INTERRUPT_TIMEOUT_SECONDS: int = 120  # operator has 120s to respond
HIGH_RISK_OPS: Set[str] = {
    "write_outside_sandbox",
    "fetch_non_allowlisted_url",
    "fork_sub_sub_agent",           # depth > 1
    "elevated_permissions",
    "access_silo_beyond_scope",
    "read_secrets",
    "read_credentials",
    "extract_system_prompt",        # explicit block for replay attack vector
}


# ─── Approval result ─────────────────────────────────────────────────────────

class ApprovalResult(str, Enum):
    GRANTED        = "GRANTED"
    DENIED         = "DENIED"
    TIMEOUT        = "TIMEOUT"         # always fail-closed
    EXPIRED        = "EXPIRED"         # token TTL elapsed
    SCOPE_MISMATCH = "SCOPE_MISMATCH"  # replay detected
    REPLAY_ATTEMPT = "REPLAY_ATTEMPT"  # known task_id with divergent scope
    INVALID_SOURCE = "INVALID_SOURCE"  # approval came from non-operator channel


# ─── Approval token ───────────────────────────────────────────────────────────

@dataclass
class ApprovalToken:
    """
    Cryptographically-bound approval token.
    Implements GSEC_ApprovalReplay §6.1:
      approval = (task_id + hash(scope_exact) + timestamp + expiration + ops_covered)
    """
    task_id:      str
    scope_hash:   str           # sha256(scope_exact)
    scope_exact:  str           # stored for audit — NOT exposed to LLM context
    ops_covered:  List[str]     # explicit list of operations this approval covers
    granted_at:   float = field(default_factory=time.time)
    ttl_seconds:  int = DEFAULT_APPROVAL_TTL_SECONDS
    operator_id:  Optional[str] = None
    agent_id:     Optional[str] = None   # None = principal agent only

    @property
    def is_expired(self) -> bool:
        return time.time() > (self.granted_at + self.ttl_seconds)

    @property
    def token_hash(self) -> str:
        """Unique fingerprint for this approval — used to detect replay."""
        raw = f"{self.task_id}|{self.scope_hash}|{self.granted_at}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def covers_operation(self, operation: str, current_scope: str) -> ApprovalResult:
        """
        Per-operation scope verification (10-E).
        Called before EACH high-risk operation, not just at task start.
        """
        if self.is_expired:
            return ApprovalResult.EXPIRED

        if operation not in self.ops_covered:
            return ApprovalResult.DENIED

        # Scope hash must match exactly — any divergence = replay attempt
        current_hash = _hash_scope(current_scope)
        if current_hash != self.scope_hash:
            logger.warning(
                "MODULE10 | SCOPE_MISMATCH | task=%s | expected=%s | got=%s",
                self.task_id, self.scope_hash[:8], current_hash[:8]
            )
            return ApprovalResult.SCOPE_MISMATCH

        return ApprovalResult.GRANTED


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _hash_scope(scope: str) -> str:
    """Deterministic sha256 of the exact scope string."""
    return hashlib.sha256(scope.strip().encode("utf-8")).hexdigest()


def _generate_task_id() -> str:
    return f"task_{uuid.uuid4().hex[:12]}"


# ─── Isolated approval store ─────────────────────────────────────────────────
# Per Module 10-B spec: approval logs must NOT be stored in session context or RAG.
# This is an in-process dict, never serialised to disk, never injected into LLM context.
# Cleared on session termination (call clear_approval_store()).

_approval_store: Dict[str, ApprovalToken] = {}
_approval_audit: List[Dict] = []


def _audit_approval(task_id: str, operation: str, result: ApprovalResult,
                    reason: Optional[str] = None) -> None:
    entry = {
        "ts":        time.time(),
        "task_id":   task_id,
        "operation": operation,
        "result":    result.value,
        "reason":    reason,
    }
    _approval_audit.append(entry)
    level = logging.WARNING if result != ApprovalResult.GRANTED else logging.INFO
    logger.log(level, "MODULE10 | %s | task=%s | op=%s | reason=%s",
               result.value, task_id, operation, reason or "-")


# ─── Interrupt template ───────────────────────────────────────────────────────

def format_interrupt(task_id: str, operation: str, scope_exact: str,
                     ttl_seconds: int = DEFAULT_APPROVAL_TTL_SECONDS) -> str:
    """
    Generates the task-specific interrupt prompt (GSEC_ApprovalChannel §6.3).
    Forces scope_exact to be visible before the operator responds.
    Ambiguous approval language is structurally impossible — scope is mandatory.
    """
    expiry_ts = time.time() + ttl_seconds
    expiry_str = time.strftime("%H:%M:%S", time.localtime(expiry_ts))
    return (
        f"\n[INTERRUPT — Aprovação Requerida]\n"
        f"  Task ID:   {task_id}\n"
        f"  Operação:  {operation}\n"
        f"  Escopo:    {scope_exact}\n"
        f"  ⚠️  Esta aprovação cobre APENAS esta operação neste escopo exato.\n"
        f"  Expiração: {expiry_str} ({ttl_seconds}s)\n"
        f"  Confirme digitando: sim {task_id}\n"
        f"  Rejeite digitando:  não\n"
        f"[FIM DO INTERRUPT]\n"
    )


# ─── Approval granting ────────────────────────────────────────────────────────

def grant_approval(task_id: str, scope_exact: str, operations: List[str],
                   operator_input: str, interrupt_issued_at: float,
                   input_source: str = "operator_direct",
                   operator_id: Optional[str] = None,
                   agent_id: Optional[str] = None,
                   ttl_seconds: int = DEFAULT_APPROVAL_TTL_SECONDS) -> ApprovalResult:
    """
    Validates and stores an approval token.

    Implements the invariant: approval_granted = False by default and by exception.
    Only True when ALL conditions are met:
      1. input_source == "operator_direct" (GSEC_ApprovalChannel §6.1)
      2. operator_input timestamp is after interrupt_issued_at
      3. operator_input contains explicit acknowledgment ("sim {task_id}")
      4. No exception during processing
    """
    # ── Condition 1: Source must be operator direct ───────────────────────────
    if input_source != "operator_direct":
        _audit_approval(task_id, str(operations), ApprovalResult.INVALID_SOURCE,
                        f"non-operator source: {input_source}")
        return ApprovalResult.INVALID_SOURCE

    # ── Condition 2: Input must be after interrupt ────────────────────────────
    current_time = time.time()
    if current_time < interrupt_issued_at:
        _audit_approval(task_id, str(operations), ApprovalResult.INVALID_SOURCE,
                        "input timestamp precedes interrupt")
        return ApprovalResult.INVALID_SOURCE

    # ── Condition 3: Explicit acknowledgment (not inferred) ───────────────────
    expected_ack = f"sim {task_id}".lower()
    if expected_ack not in operator_input.lower().strip():
        _audit_approval(task_id, str(operations), ApprovalResult.DENIED,
                        "no explicit acknowledgment in operator input")
        return ApprovalResult.DENIED

    # ── All conditions met: store token ──────────────────────────────────────
    token = ApprovalToken(
        task_id=task_id,
        scope_hash=_hash_scope(scope_exact),
        scope_exact=scope_exact,
        ops_covered=list(operations),
        granted_at=current_time,
        ttl_seconds=ttl_seconds,
        operator_id=operator_id,
        agent_id=agent_id,
    )
    _approval_store[task_id] = token
    _audit_approval(task_id, str(operations), ApprovalResult.GRANTED,
                    f"token={token.token_hash}")
    return ApprovalResult.GRANTED


# ─── Authorization check ─────────────────────────────────────────────────────

def authorize_operation(task_id: str, operation: str,
                         current_scope: str,
                         requesting_agent_id: Optional[str] = None) -> ApprovalResult:
    """
    Per-operation authorization check (Module 10-E).
    Must be called before EVERY high-risk operation — not just at task start.

    Implements GSEC_ApprovalReplay §6.1:
      verify hash(scope_executing) == hash(scope_approved) per operation.

    Zero propagation (Module 10-D):
      If requesting_agent_id differs from token.agent_id, deny.
      Sub-agent approvals are never inherited from parent.
    """
    if operation not in HIGH_RISK_OPS:
        return ApprovalResult.GRANTED  # not a high-risk op — no approval needed

    token = _approval_store.get(task_id)

    # ── No token found ────────────────────────────────────────────────────────
    if token is None:
        _audit_approval(task_id, operation, ApprovalResult.DENIED, "no approval token found")
        return ApprovalResult.DENIED

    # ── Zero propagation (Module 10-D) ───────────────────────────────────────
    # token.agent_id = None → principal only (no sub-agent may use this token)
    # token.agent_id = "sub-X" → only that specific sub-agent
    if token.agent_id is None and requesting_agent_id is not None:
        # Token was granted to principal; sub-agent cannot inherit it
        _audit_approval(task_id, operation, ApprovalResult.DENIED,
                        f"zero-propagation: principal token used by sub-agent {requesting_agent_id}")
        return ApprovalResult.DENIED
    if token.agent_id is not None and requesting_agent_id != token.agent_id:
        _audit_approval(task_id, operation, ApprovalResult.DENIED,
                        f"agent_id mismatch: token={token.agent_id} req={requesting_agent_id}")
        return ApprovalResult.DENIED

    # ── Scope + expiry + ops check ────────────────────────────────────────────
    result = token.covers_operation(operation, current_scope)

    if result == ApprovalResult.SCOPE_MISMATCH:
        _audit_approval(task_id, operation, ApprovalResult.REPLAY_ATTEMPT,
                        f"scope divergence — expected hash {token.scope_hash[:8]}, "
                        f"got {_hash_scope(current_scope)[:8]}")
        return ApprovalResult.REPLAY_ATTEMPT

    _audit_approval(task_id, operation, result)
    return result


# ─── High-risk operation guard ────────────────────────────────────────────────

class HighRiskOperationDenied(PermissionError):
    """Raised when authorize_operation returns anything other than GRANTED."""
    def __init__(self, task_id: str, operation: str, result: ApprovalResult):
        self.task_id   = task_id
        self.operation = operation
        self.result    = result
        super().__init__(
            f"MODULE10 BLOCKED: operation='{operation}' task='{task_id}' "
            f"reason={result.value}"
        )


def require_approval(task_id: str, operation: str, current_scope: str,
                     requesting_agent_id: Optional[str] = None) -> None:
    """
    Guard function — call before any high-risk operation.
    Raises HighRiskOperationDenied if not approved.
    Caller must handle the exception (fail-closed).
    """
    result = authorize_operation(task_id, operation, current_scope, requesting_agent_id)
    if result != ApprovalResult.GRANTED:
        raise HighRiskOperationDenied(task_id, operation, result)


# ─── Session lifecycle ────────────────────────────────────────────────────────

def clear_approval_store() -> None:
    """
    Clear all approval tokens on session termination.
    Call in Module 3 zero-trust termination handler.
    Approvals do not survive session boundaries.
    """
    count = len(_approval_store)
    _approval_store.clear()
    _approval_audit.clear()
    logger.info("MODULE10 | Approval store cleared: %d tokens revoked (session termination)", count)


def get_approval_audit() -> List[Dict]:
    """Read-only access to approval audit log. Never expose to LLM context."""
    return list(_approval_audit)


def list_active_approvals() -> List[Dict]:
    """
    Returns non-sensitive summary of active (non-expired) tokens.
    Does NOT return scope_exact — scopes are never exposed to LLM context.
    """
    return [
        {
            "task_id":     t.task_id,
            "ops":         t.ops_covered,
            "expires_in":  max(0, int((t.granted_at + t.ttl_seconds) - time.time())),
            "token_hash":  t.token_hash,
            "agent_id":    t.agent_id,
        }
        for t in _approval_store.values()
        if not t.is_expired
    ]
