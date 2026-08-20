"""
Cliente LLM intercambiable. Los nodos del grafo (graph/nodes.py) dependen
de la interfaz LLMClient, no de un proveedor concreto -- así probar Kimi,
un modelo local (Ollama) u otro proveedor es implementar esta interfaz,
sin tocar la lógica de los nodos.

DeepSeek V4-Flash se mantiene como backend de producción: comparado con
Kimi para el mismo perfil de consulta, Kimi resulta más caro salvo K3,
que iguala casi a los modelos de frontera pero a 15-20x el coste de
DeepSeek Flash (tarifas punta/valle de DeepSeek desde su subida de
precios). Esta interfaz existe precisamente para no quedar atado a esa
elección si el panorama de precios vuelve a cambiar.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    # 'stop' (completado con normalidad), 'length' (cortado por
    # max_tokens -- el texto puede estar incompleto a mitad de frase),
    # u otros valores del proveedor ('content_filter', etc.). `None` si
    # el backend no lo expone (ver OllamaClient). Necesario porque una
    # respuesta truncada a mitad de frase (caso real: Shellac, tier 3)
    # se devolvía al usuario final sin ningún aviso -- ver
    # generate_answer_node, que comprueba este campo explícitamente
    # antes de dar una respuesta por buena.
    finish_reason: str | None = None


class LLMClient(ABC):
    """Interfaz mínima que necesitan los nodos del grafo."""

    @abstractmethod
    def complete(
        self,
        *,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 800,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Una llamada de completion simple, sin streaming ni tools --
        es lo único que usan los Nodos 1, 3 (fallback) y 4 tal como están
        diseñados hoy. Si en el futuro se necesita tool-calling (p.ej.
        para el servidor MCP), ampliar la interfaz, no forzarlo aquí.
        """
        raise NotImplementedError


class DeepSeekClient(LLMClient):
    """Backend de producción. API compatible OpenAI.

    Modelo por defecto: deepseek-v4-flash (ver docs/ -> STACK.json para
    el razonamiento de coste). Cambiar a "deepseek-v4-pro" es solo
    cambiar este string, misma API key, mismo base_url.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "deepseek-v4-flash",
    ):
        # Import perezoso: no forzar la dependencia de 'openai' si alguien
        # usa otro backend (p.ej. local) y no lo tiene instalado.
        from openai import OpenAI

        self.model = model
        self._client = OpenAI(
            api_key=api_key or os.environ["DEEPSEEK_API_KEY"],
            base_url=base_url or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )

    def complete(
        self,
        *,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 800,
        temperature: float = 0.0,
    ) -> LLMResponse:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            # DeepSeek V4 activa 'thinking' (esfuerzo 'high') por defecto:
            # gasta max_tokens en reasoning_content antes del texto final
            # (riesgo de truncamiento) e ignora silenciosamente temperature.
            # Lo desactivamos para que temperature=0.0 aplique de verdad y
            # el coste real se acerque a la estimación de docs/.
            extra_body={"thinking": {"type": "disabled"}},
        )
        choice = response.choices[0]
        usage = response.usage
        return LLMResponse(
            text=choice.message.content or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            model=self.model,
            finish_reason=choice.finish_reason,
        )


class OllamaClient(LLMClient):
    """Backend local, opcional -- para quien clone el repo y quiera
    correrlo sin API de pago (coste cero, calidad menor; no es el
    backend por defecto porque sigue las reglas del Nodo 4 de forma
    menos fiable que DeepSeek).

    Requiere tener Ollama corriendo localmente (`ollama serve`) y el
    modelo ya descargado (`ollama pull llama3.1` o el que se prefiera).
    """

    def __init__(self, model: str = "llama3.1", base_url: str = "http://localhost:11434"):
        import requests  # noqa: F401  -- valida que la dependencia existe pronto, no en el primer complete()

        self.model = model
        self.base_url = base_url

    def complete(
        self,
        *,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 800,
        temperature: float = 0.0,
    ) -> LLMResponse:
        import requests

        resp = requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data.get("message", {}).get("content", "")
        # Ollama no siempre devuelve conteo de tokens homogéneo entre
        # versiones; se deja en 0 si no está disponible en vez de fallar.
        # `done_reason` ("stop"/"length"/...) existe en versiones
        # recientes de la API -- `None` si no está presente, no asumido.
        return LLMResponse(
            text=text,
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            model=self.model,
            finish_reason=data.get("done_reason"),
        )


def build_default_client() -> LLMClient:
    """Fábrica usada por graph/build.py. Lee EFSA_RAG_LLM_BACKEND del
    entorno ('deepseek' por defecto, 'ollama' como alternativa local).
    """
    backend = os.environ.get("EFSA_RAG_LLM_BACKEND", "deepseek").lower()
    if backend == "deepseek":
        return DeepSeekClient()
    if backend == "ollama":
        return OllamaClient()
    raise ValueError(f"Backend LLM desconocido: {backend!r}")