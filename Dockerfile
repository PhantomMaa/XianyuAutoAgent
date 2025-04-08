FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Set timezone to Asia/Shanghai (UTC+8)
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install NodeJS 18
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# 安装 uv 并使用它来安装依赖
RUN pip install --no-cache-dir uv && \
    uv pip install --system -r requirements.txt && \
    python -m playwright install chromium --with-deps

# Copy application code
COPY . .

# Run the application
CMD ["python", "main.py"]
