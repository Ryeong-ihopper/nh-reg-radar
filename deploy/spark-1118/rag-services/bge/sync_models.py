from huggingface_hub import snapshot_download


for model in ("BAAI/bge-m3", "BAAI/bge-reranker-v2-m3"):
    print(snapshot_download(model), flush=True)
