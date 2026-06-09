FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: run pipeline with example spec (override with docker run args)
ENTRYPOINT ["python", "run_pipeline.py"]
CMD ["specs/example_spec.yaml"]
