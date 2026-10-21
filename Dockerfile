# Imagen base ligera con version fija
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencias primero (aprovecha la cache si solo cambia el codigo)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Codigo y prompts (el modelo NO se copia: vive en el servidor Ollama)
COPY src/ ./src/
COPY prompts/ ./prompts/

# Usuario no root; results/ escribible por ese usuario
RUN useradd --create-home appuser \
    && mkdir -p /app/results \
    && chown -R appuser:appuser /app
USER appuser

ENV OLLAMA_HOST=http://host.docker.internal:11434

ENTRYPOINT ["python", "src/inference.py"]
CMD ["--help"]
