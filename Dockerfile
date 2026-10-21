# Backend API (FastAPI). Dữ liệu đọc từ Postgres (dịch vụ db); mô hình xếp hạng và cache PDF ở volume /data.
FROM python:3.13-slim

WORKDIR /srv
ENV PYTHONUNBUFFERED=1 \
    PAPERREC_DATA_DIR=/data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Chỉ các package backend cần lúc chạy (crawler: client OpenReview để tải PDF)
COPY common ./common
COPY appdb ./appdb
COPY recsys ./recsys
COPY features ./features
COPY crawler ./crawler
COPY api ./api

EXPOSE 8000
CMD ["python", "-m", "api", "--host", "0.0.0.0", "--port", "8000"]
