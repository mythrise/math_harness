FROM python:3.11-slim-bookworm
WORKDIR /opt/cumcm
COPY pyproject.toml ./
RUN python -c "import subprocess,sys,tomllib; p=tomllib.load(open('pyproject.toml','rb')); subprocess.check_call([sys.executable,'-m','pip','install','--no-cache-dir',*p['build-system']['requires'],'wheel',*p['project']['dependencies']])"
COPY cumcm_harness ./cumcm_harness
COPY .agents/skills ./.agents/skills
COPY docs/materials-upgrade/source-model-catalog.json ./docs/materials-upgrade/source-model-catalog.json
COPY vendor/mosaic_v14 ./vendor/mosaic_v14
COPY vendor/MANIFEST.json ./vendor/MANIFEST.json
RUN pip install --no-cache-dir --no-deps --no-build-isolation -e . && chmod -R a+rX /opt/cumcm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPLBACKEND=Agg
CMD ["python", "-m", "cumcm_harness", "--help"]
