FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

# Install system dependencies for weasyprint
RUN apt-get update && apt-get install -y \
    libglib2.0-dev \
    libpango1.0-dev \
    libcairo2-dev \
    libgdk-pixbuf-xlib-2.0-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd -m -u 1000 runner
USER runner
HEALTHCHECK CMD netstat -an | grep "8080"

# Copy source code
COPY . .

# Set AWS region environment variable
ENV AWS_REGION=us-west-2
ENV DISABLE_CALLBACK_HANDLER=1
ENV GET_INFO_LOGS=1

EXPOSE 8080

# Set PYTHONPATH to include current directory
ENV PYTHONPATH=/app

CMD ["opentelemetry-instrument", "python", "-m", "wind_farm_dev_agent"]
# CMD ["python", "-m", "wind_farm_dev_agent"]