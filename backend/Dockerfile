FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Prophet (needs C++ compiler for CmdStan)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install PyTorch CPU-only version first (smaller than GPU version)
# This is needed for TFT (Temporal Fusion Transformer) model
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install remaining requirements
RUN pip install --no-cache-dir -r requirements.txt

# Install CmdStan for Prophet (required for Prophet 1.1+)
RUN python -m cmdstanpy.install_cmdstan --cores 2

# Fix Prophet's cmdstan path - Prophet looks for cmdstan in its own package directory
# but we installed it system-wide. Create symlink to fix this.
RUN CMDSTAN_VERSION=$(ls /root/.cmdstan/ | head -1) && \
    rm -rf /usr/local/lib/python3.11/site-packages/prophet/stan_model/cmdstan-* && \
    ln -s /root/.cmdstan/$CMDSTAN_VERSION /usr/local/lib/python3.11/site-packages/prophet/stan_model/cmdstan-2.31.0

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
