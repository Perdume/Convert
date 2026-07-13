FROM python:3.12-slim

# LibreOffice: PPT/ODT -> PDF 변환 엔진, noto-cjk: 한글 폰트 (없으면 한글이 깨짐)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-impress libreoffice-writer fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app app
COPY static static

# 업로드/변환 파일은 컨테이너 내부 임시 경로에만 저장됨 (자동 삭제)
ENV CONVERT_DATA_DIR=/tmp/convert-data

# 컨테이너는 비루트 사용자로 실행
RUN useradd -m converter
USER converter

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
