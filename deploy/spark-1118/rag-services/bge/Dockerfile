FROM vllm-node:latest

RUN python3 -m pip install --no-cache-dir \
    sentence-transformers==5.7.0 \
    safetensors==0.8.0 \
    tokenizers==0.22.2

WORKDIR /app
COPY dgx_bge_server.py /app/dgx_bge_server.py
COPY sync_models.py /app/sync_models.py
ENTRYPOINT ["python3", "-u", "/app/dgx_bge_server.py"]
