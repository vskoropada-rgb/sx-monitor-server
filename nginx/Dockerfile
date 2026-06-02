FROM alpine:3.19
RUN apk add --no-cache nginx nginx-mod-http-headers-more openssl

# Self-signed сертифікат (10 років). Замінюється справжнім (Let's Encrypt тощо)
# монтуванням volume на /etc/nginx/certs з файлами self.crt + self.key.
RUN mkdir -p /etc/nginx/certs && \
    openssl req -x509 -nodes -newkey rsa:2048 -days 3650 \
        -keyout /etc/nginx/certs/self.key \
        -out /etc/nginx/certs/self.crt \
        -subj "/CN=sx-monitor" >/dev/null 2>&1

COPY nginx.conf /etc/nginx/nginx.conf
COPY errors/ /etc/nginx/errors/
EXPOSE 80 443
CMD ["nginx", "-g", "daemon off;"]
