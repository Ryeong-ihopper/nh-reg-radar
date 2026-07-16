"""Provider-neutral HTTP boundaries shared by backend and worker."""

from nh_ad_ai_providers.embeddings import EmbeddingProviderError, OpenAICompatibleEmbeddings

__all__ = ["EmbeddingProviderError", "OpenAICompatibleEmbeddings"]
