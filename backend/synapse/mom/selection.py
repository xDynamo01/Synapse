"""Local, deterministic operation classification; never executes model instructions."""
from __future__ import annotations

import re
import unicodedata

from synapse.mom.contracts import Operation


def requires_plan(message: str) -> bool:
    """Conservative deterministic escalation; never infers Swarm activation."""
    instruction = message.split("```", 1)[0].split("\n\n", 1)[0][:1000].lower()
    if re.search(r"^(replaneje|revise o plano|ajuste o plano|replan)\b", instruction):
        return True
    if not re.search(r"\b(crie|desenvolva|implemente|construa|build|develop|implement)\b", instruction):
        return False
    domains = (r"\bbackend\b", r"\bfrontend\b", r"\b(?:testes|tests)\b",
               r"\b(?:documentacao|documentação|documentation)\b", r"\b(?:imagens|visuais|images)\b")
    return sum(bool(re.search(pattern, instruction)) for pattern in domains) >= 2


def classify_operation(message: str, recent_intent: str | None = None) -> Operation:
    # Classify the user's leading request, not quoted documents or code payloads.
    instruction = message.split("```", 1)[0].split("\n\n", 1)[0][:1000]
    instruction = "".join(char for char in unicodedata.normalize("NFKD", instruction.lower())
                          if not unicodedata.combining(char))
    patterns = (
        (Operation.SUMMARY, r"\b(resuma|resumir|resumo|sintetize|sumarize|summarize|summary|tldr)\b"),
        (Operation.REVIEW, r"\b(revise|revisar|revisao|review|critique|avalie|verifique)\b"),
        (Operation.CODING, r"\b(codigo|programa|programar|programacao|implemente|implementar|funcao|script|debug|bug|python|javascript|typescript|sql|html|css|print|array|refatore|code|coding|function)\b"),
        (Operation.REASONING, r"\b(planeje|planejar|plano|raciocinio|compare|comparar|calcule|calcular|estrategia|tradeoff|plan|reason|calculate)\b"),
    )
    for operation, pattern in patterns:
        if re.search(pattern, instruction):
            return operation
    if recent_intent and re.search(
        r"^(agora|continue|continuar|melhore|deixe|faca isso|now|continue|improve)\b", instruction
    ):
        try:
            return Operation(recent_intent)
        except ValueError:
            pass
    return Operation.CONVERSATION
