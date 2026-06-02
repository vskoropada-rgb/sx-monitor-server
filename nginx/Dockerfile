FROM alpine:3.19
RUN apk add --no-cache nginx nginx-mod-http-headers-more
COPY nginx.conf /etc/nginx/nginx.conf
COPY errors/ /etc/nginx/errors/
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
