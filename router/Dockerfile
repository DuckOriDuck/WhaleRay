FROM nginx:latest

# 기본 설정 제거
RUN rm /etc/nginx/conf.d/default.conf

# 작성하신 설정을 이미지 안으로 복사
COPY nginx.conf /etc/nginx/nginx.conf