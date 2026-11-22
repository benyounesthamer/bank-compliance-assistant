# Bank Compliance Assistant: web demo image (used for the Hugging Face Space).
# The circulars are downloaded from bct.gov.tn and indexed at build time, so the demo starts ready.
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY data ./data
COPY eval ./eval
# PDFs (5 MB) + embedding and reranker models (~0.8 GB) + vector index
RUN bankrag download && bankrag index && chmod -R a+rX /app

# The demo spends the owner's API quota: live requests are limited per visitor.
# The four example policies are served from saved results and are always available.
ENV DEMO_LIVE_REQUESTS_PER_HOUR=5 \
    BANKRAG_PROVIDER=groq \
    BANKRAG_MODEL=openai/gpt-oss-20b

EXPOSE 7860
CMD ["uvicorn", "bankrag.api:app", "--host", "0.0.0.0", "--port", "7860"]
