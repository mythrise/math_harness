FROM python:3.11-slim-bookworm
WORKDIR /opt/cumcm
COPY pyproject.toml ./
COPY cumcm_harness ./cumcm_harness
COPY vendor/mosaic_v14 ./vendor/mosaic_v14
COPY vendor/MANIFEST.json ./vendor/MANIFEST.json
RUN pip install --no-cache-dir -e . && chmod -R a+rX /opt/cumcm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPLBACKEND=Agg
CMD ["python", "-m", "cumcm_harness", "--help"]
