# Security Policy

## Supported Versions

Currently, only the following versions are supported for security updates:

| Version | Supported          |
| ------- | ------------------ |
| 2.0.x   | :white_check_mark: |
| < 2.0.0 | :x:                |

## Reporting a Vulnerability

The S.O.H.-X project takes security very seriously. If you discover a potential vulnerability, please **DO NOT** open a public issue. Instead, follow these steps:

1. Send a detailed report to the maintenance team at: **clovesnascimento@proton.me** (or the contact provided in CNGSM documentation).
2. Include a description of the vulnerability, the module affected (Cortex, Managed Layer, G-SEC), and a Proof of Concept (PoC) if possible.
3. We will respond within 48 to 72 hours to acknowledge the report and coordinate a fix.

### G-SEC Disclosure Policy

As part of our commitment to the **G-SEC (Omega-9 / Alpha-10)** philosophy:
- We follow a responsible disclosure policy.
- We request that you do not disclose the vulnerability publicly until a mitigation or patch has been released.
- Credits will be given to researchers who contribute to the hardening of the Strait of Hormuz ecosystem.

## Security Architecture (G-SEC)

This project implements proactive defense layers:
- **Omega-9**: Structural isolation and sanitization of prompt context.
- **Alpha-10**: Local filesystem sandboxing for agent execution.
- **LLM-as-Judge**: Real-time validation of model outputs against injection patterns.

For more details on our defensive posture, consult the `🛡️ 6. Segurança e Hardening` section in the [README.md](README.md).
