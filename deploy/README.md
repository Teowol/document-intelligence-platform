# Deploy konfigürasyonu (Phase 10)

Bu klasör üretim ortamına hazırlık dosyalarını içerir. Proje öğrenim amaçlı
olduğundan canlı bir sunucuya yayınlanmıyor; ancak aşağıdaki adımlar, gerçek
bir sunucuya taşırsan uygulanabilir.

## Hızlı başlangıç (local, HTTP olmadan test)

```bash
cp .env.prod .env
# SECRET_KEY ve DB şifrelerini güncelle
docker compose --profile with-nginx up -d --build
```

> `deploy/nginx.conf` 443 HTTPS bloğu içerir; yerel test için sertifika yoksa
> 80'e len Türkçe 443 bloğunu kaldırman ya da sertifika kurman gerekir.

## Let's Encrypt (SSL) kurulumu

Gerçek bir domain ve DNS + 80/443 açık değilse yapma. Hazır olduğunda:

```bash
# nginx'e 80'den TLS yönlendirmesi öncesinde sertifika al
docker run -it --rm -v "$PWD/deploy/tls-certs:/etc/letsencrypt" \
  -p 80:80 certbot/certbot certonly --standalone -d your-domain.com
# yayınlanmasını bekle, sonra deploy/nginx.conf içindeki cert yollarını kontrol et
docker compose restart nginx
```

TLS sertifikaları `deploy/tls-certs` altına iner (`.dockerignore` ve `.gitignore`
ile dışlandı, asla commit etme).

## Yedekleme & geri yükleme

```bash
./scripts/backup.sh            # backups/db/*.dump + backups/media/*.tar.gz
./scripts/restore.sh backups/db/document_intelligence_XXXXXXXX.dump
```

## Flower (kuyruk izleme)

```bash
docker compose up -d flower
# http://<host>:5555/flower  (FLOWER_USER / FLOWER_PASSWORD)
```

## CI/CD

`.github/workflows/ci.yml` her push'ta lint + test + image build çalıştırır.
