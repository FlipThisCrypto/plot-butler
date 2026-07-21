FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends openssh-client rsync iproute2 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY plot_butler.py index.html ./
ENV PLOT_BUTLER_BIND=0.0.0.0 PLOT_BUTLER_PORT=8088
EXPOSE 8088
# Note: host networking / mounts required for nvidia-smi, journals, staging paths
CMD ["python3","plot_butler.py"]
