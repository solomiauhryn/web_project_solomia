set -e

mkdir -p /etc/nginx/ssl

if [ ! -f /etc/nginx/ssl/selfsigned.crt ]; then
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/nginx/ssl/selfsigned.key \
        -out /etc/nginx/ssl/selfsigned.crt \
        -subj "/C=UA/ST=Lviv/L=Lviv/O=University/OU=CS/CN=localhost"
fi

exec nginx -g "daemon off;"
