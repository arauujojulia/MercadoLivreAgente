"""
Cliente da API Groq — o "cérebro" de linguagem do agente.

Importante: nunca envia o dataset bruto de pedidos para o LLM. Só recebe
agregados já calculados pelo Financial Engine / Forecast Engine. Isso
reduz custo de tokens, latência, e evita expor dado sensível de
faturamento linha a linha em prompts.
"""

from __future__ import annotations

from groq import Groq

from config.settings import get_secret

MODEL_NAME = "llama-3.3-70b-versatile"  # ajustar conforme modelo disponível na conta Groq

SYSTEM_PROMPT = """\
Você é um analista financeiro especialista em e-commerce, atuando dentro de \
um agente de gestão para uma loja do Mercado Livre. Você recebe métricas já \
agregadas (nunca dados brutos linha a linha) e deve gerar respostas curtas, \
diretas e acionáveis em português do Brasil. Sempre que possível, aponte uma \
recomendação prática, não apenas a descrição do número.\
"""


def _get_client() -> Groq:
    api_key = get_secret("groq_api_key")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY não configurada. Configure nas preferências do app.")
    return Groq(api_key=api_key)


def build_aggregate_context(kpis: dict, top_sellers, worst_sellers, forecast_df) -> str:
    """Monta um resumo textual compacto dos agregados para enviar ao LLM."""
    lines = [
        f"Faturamento bruto: R$ {kpis['gross_revenue']:.2f}",
        f"Faturamento líquido: R$ {kpis['net_revenue']:.2f}",
        f"Margem líquida: {kpis['margin_pct']:.1f}%",
        f"Pedidos no período: {kpis['orders_count']}",
        f"Ticket médio: R$ {kpis['avg_ticket']:.2f}",
    ]
    if not top_sellers.empty:
        lines.append("Top produtos (por lucro líquido): " + ", ".join(top_sellers["item_title"].head(5).tolist()))
    if not worst_sellers.empty:
        lines.append("Produtos com pior desempenho: " + ", ".join(worst_sellers["item_title"].head(5).tolist()))
    if forecast_df is not None and not forecast_df.empty:
        total_forecast = forecast_df["predicted_net_revenue"].sum()
        lines.append(f"Previsão de faturamento líquido para os próximos {len(forecast_df)} dias: R$ {total_forecast:.2f}")
    return "\n".join(lines)


def generate_insights(context: str) -> str:
    """Pede ao Groq um resumo executivo em linguagem natural a partir dos agregados."""
    client = _get_client()
    completion = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Aqui estão os números atuais da loja:\n\n{context}\n\n"
                f"Gere um resumo executivo de até 6 linhas com os pontos mais importantes "
                f"e uma recomendação prática.",
            },
        ],
        temperature=0.3,
        max_tokens=500,
    )
    return completion.choices[0].message.content


def answer_free_question(question: str, context: str, chat_history: list[dict] | None = None) -> str:
    """Chat livre do usuário com o agente, sempre ancorado nos agregados atuais."""
    client = _get_client()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.append({"role": "system", "content": f"Contexto atual da loja:\n{context}"})
    if chat_history:
        messages.extend(chat_history)
    messages.append({"role": "user", "content": question})

    completion = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        temperature=0.4,
        max_tokens=600,
    )
    return completion.choices[0].message.content
