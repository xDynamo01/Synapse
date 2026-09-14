"""Local, deterministic operation classification; never executes model instructions."""
from __future__ import annotations

import re
import unicodedata

from synapse.mom.contracts import Operation


def classify_operation(message: str) -> Operation:
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
    return Operation.CONVERSATION
