"""Thin wrapper around the Jina AI embeddings API, used for semantic todo search."""
import requests
import streamlit as st

JINA_EMBEDDINGS_URL = "https://api.jina.ai/v1/embeddings"


def get_embedding(text: str) -> list[float] | None:
    """Return a single embedding vector for `text`, or None if the call fails."""
    api_key = os.getenv("JINA_KEY")
    model = st.secrets["jina"].get("embedding_model", "jina-embeddings-v2-base-en")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": model, "input": [text]}

    try:
        resp = requests.post(JINA_EMBEDDINGS_URL, json=payload, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        return data["data"][0]["embedding"]
    except Exception as e:
        st.warning(f"Jina embedding request failed, continuing without embedding: {e}")
        return None
