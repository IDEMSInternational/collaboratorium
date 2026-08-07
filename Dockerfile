FROM python:3.12-slim

WORKDIR /app

# Copy only requirements first for better Docker layer caching
COPY requirements.txt /app/requirements.txt

RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY assets/ /app/assets/
COPY pyproject.toml /app/pyproject.toml
COPY src/ /app/src/

# Installed rather than run from source, so plugins resolve through the
# pantograph.plugins entry points.
RUN pip install --no-cache-dir --no-deps -e /app

EXPOSE 8050

ENTRYPOINT ["python", "-m", "pantograph"]
