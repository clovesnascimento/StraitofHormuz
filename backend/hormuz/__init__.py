# -*- coding: utf-8 -*-
# ┌─────────────────────────────────────────────────────────────────────────┐
# │  ⚓  Agente Hormuz                                                           
# │  Criador    : Cloves Nascimento                                                  
# │  Papel      : Arquiteto de Ecossistemas Cognitivos                                                     
# │  Org        : CNGSM - Cognitive Neural & Generative Systems Management                                                      
# │  Versão     : 1.0.0                                                  
# │  Fingerprint: 8a3ee43b0c78e2b4                                              
# │  SHA-256    : 8a3ee43b0c78e2b4cb77204ffc5fb4ed6a33d8f90af59435d19533d9739c7d00                                                   
# │                                                                          
# │  © 2025 Cloves Nascimento — Todos os direitos reservados.                     
# │  Distribuição e modificação sujeitas aos termos da licença CNGSM.       
# └─────────────────────────────────────────────────────────────────────────┘

from .core.identity import (
    IDENTITY,
    FINGERPRINT,
    VERSION,
    verify_identity,
    attribution_header,
    embed_in_output,
    extract_watermark,
)

# Identity verified at package import — strict mode: raises RuntimeError if tampered
verify_identity(strict=True)

__version__     = VERSION
__author__      = IDENTITY["creator"]
__role__        = IDENTITY["role"]
__org__         = IDENTITY["org"]
__product__     = IDENTITY["product"]
__fingerprint__ = FINGERPRINT

__all__ = [
    "__version__", "__author__", "__role__", "__org__",
    "__product__", "__fingerprint__",
    "verify_identity", "attribution_header",
    "embed_in_output", "extract_watermark",
]
