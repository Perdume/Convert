FROM python:3.12-slim

# LibreOffice(writer/impress/calc): 오피스·한글 문서 변환 엔진, noto-cjk: 한글 폰트
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-impress libreoffice-writer libreoffice-calc fonts-noto-cjk \
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
# PORT: 클라우드(Render 등)가 지정하는 포트. --proxy-headers: 프록시 뒤에서
# 실제 방문자 IP를 인식해 IP별 레이트리밋이 정상 작동하게 한다.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips '*'"]
