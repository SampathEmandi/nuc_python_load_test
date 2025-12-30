# Use Python 3.12 as base image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install uv (fast Python package installer)
RUN pip install uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen

# Copy your app code into the container
COPY . .

# Expose the FastAPI port
EXPOSE 8000

# Run the FastAPI app with reload
# Use uv run to execute uvicorn in the virtual environment
CMD uv run uvicorn api:app --host 0.0.0.0 --port 8000

