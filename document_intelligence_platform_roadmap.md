# AI Destekli Araştırma & Doküman İstihbaratı Platformu — İnşa Yol Haritası

**Versiyon:** 1.0 — Ekim 2026
**Yaklaşım:** Sıfırdan, katman katman (her faz bağımsız olarak doğrulanabilir şekilde kapanır)
**Yığın:** Python · Django · PostgreSQL/pgvector · OpenAI (gpt-4o-mini + text-embedding-3-small) · Redis · Celery · Docker Compose · NGINX · Gunicorn

---

## 1. Proje Özeti

Kullanıcıların **PDF, Excel, CSV, TXT ve Markdown** dosyalarını yükleyip **semantik arama** yapabildiği ve yalnızca kendi dokümanlarından beslenen, **kaynak gösteren (grounded) soru-cevap** alabildiği güvenli bir platform. Tüm doküman işleme (ayrıştırma → parçalama → embedding) asenkron çalışır; yetkilendirme (RBAC) hem arayüzde hem de arama motorunda korunur.

---

## 2. Hedef Mimari (Genel Bakış)

```
                       ┌──────────────────────────────────────────────┐
  Tarayıcı ──────────► │ NGINX (TLS/HTTP2, statik, reverse proxy)     │
                       └───────────────┬──────────────────────────────┘
                                       │
                       ┌───────────────▼──────────────────────────────┐
                       │  Web  —  Gunicorn + Django (Templates + APP) │
                       │  · Upload / RBAC / Chat / Arama              │
                       └───────┬──────────────────┬───────────────────┘
                               │                  │
                    ┌──────────▼───────┐  ┌───────▼─────────┐
                    │ PostgreSQL+pgvector│ │ Redis (broker + │
                    │ · ilişkisel veri   │ │ cache)          │
                    │ · vektör arama     │ └───────┬─────────┘
                    └──────────┬────────┘         │
                               │                  │
                    ┌──────────▼───────┐  ┌───────▼─────────┐
                    │ Celery Worker    │◄─┤ Celery Beat     │
                    │ parse·chunk·embed│  │ (bakım işleri)  │
                    └──────────┬───────┘  └─────────────────┘
                               │
                    ┌──────────▼─────────────────────────────┐
                    │        OpenAI API                      │
                    │ · embeddings (text-embedding-3-small)  │
                    │ · chat + function calling (gpt-4o-mini)│
                    └────────────────────────────────────────┘
```

- **İş akışı:** Dosya yükle → doğrula → kaydet → Celery görevi: ayrıştır → normalize et → parçala → embedding üret → pgvector'a yaz → durum güncelle.
- **Soru-cevap akışı:** Soru → embedding → vektör arama (yetki filtreli) → bağlam derleme → gpt-4o-mini function calling döngüsü → kaynak gösteren yanıt.

---

## 3. Bulut Sağlayıcı Önerisi (Free / Uygun Fiyatlı)

Bu yığının (PostgreSQL+pgvector + Redis + en az 2 Celery worker + NGINX + Gunicorn) rahat çalışabilmesi için **en az 3–4 GB RAM** gerekir. 1 GB'lik dropletta Celery worker'lar OOM ile ölür. Buna göre önerim:

| Sağlayıcı | Maliyet | Artılar | Eksiler | Uygunluk |
|---|---|---|---|---|
| **Hetzner (CX22)** — *birincil öneri* | ~4 €/ay (2 vCPU, 4 GB RAM, 40 GB NVMe) | Tüm stack tek VPS'ta Docker Compose ile; en iyi performans/fiyat; ek kaynak ucuz | Kurulum ve bakım tamamen sizde | **Üretim + öğrenme** ✓ |
| **Oracle Cloud "Always Free" (Ampere A1)** | 0 ₺ (kalıcı ücretsiz: 4 OCPU + 24 GB RAM toplam) | Gerçekten ücretsiz ve bu yığın için yeterince güçlü | Kayıt sırasında kart ister; ARM mimarisi (çok az uyum sorunu); bölgeye göre stok | **Ücretsiz öğrenme/demo** ✓ |
| DigitalOcean Droplet | ~18–24 $/ay (4–8 GB) | Kurulumu en kolay, döküman bol | Fiyat/performans olarak Hetzner'ın gerisinde | Alternatif üretim |
| Railway / Render | Ücretsiz katman kısıtlı (sleep; Postgres ücretsiz süre sınırlı) | Konfigürasyon az | Celery + Redis kalıcı çalıştırmak pahalı/garip; 1 GB RAM sınırı sorun | Yalnızca hızlı demo |
| AWS/Azure/GCP Free Tier | 12 ay ücretsiz dene | Tanıdık ekosistem | Ücretsiz dönem bitince pahalı; t2.micro (1 GB) bu stack için yetersiz | Tavsiye edilmez |

**Sonuç tavsiyesi:**
- **Geliştirme:** Günde gelen her şeyi lokal Docker Compose'da yapın (maliyet 0).
- **İlk deploy (öğrenme/demo):** Oracle Always Free veya Render ücretsiz katmanı.
- **Gerçek kullanım/üretim:** Hetzner CX22 (gerekirse CX32/8 GB'a büyütürsünüz) + Docker Compose + Let's Encrypt. Fiyatlar 2026'ya göre yaklaşıktır, kaydolmadan önce güncel fiyatı doğrulayın.

---

## 4. Teknoloji Yığını — Karar Listesi

| Bileşen | Seçim | Not |
|---|---|---|
| Dil & Framework | Python 3.12+ · **Django 5.2 LTS** | LTS uzun destek; güncel sürüme geçiş opsiyonel |
| Veritabanı | PostgreSQL 16 + **pgvector** (`pgvector/pgvector:pg16` imajı) | Hem ilişkisel veri hem vektör — ayrı vektör DB'si gerekmez |
| Message broker / Cache | Redis 7 | Celery broker'ı + önbellek + rate-limit sayaçları |
| Asenkron işleme | Celery 5 + `django-celery-beat` + Flower | Doküman işleme kuyruğu; izleme için Flower |
| Kullanıcı & kimlik | Django custom User + `django-allauth` | Custom User **ilk günden** (bkz. §7) |
| RBAC | Rol alanı + Django Groups + sahiplik kontrolü | İleride `django-guardian` ile nesne izinleri eklenebilir |
| LLM — sohbet | **gpt-4o-mini** (function calling destekli) | Maliyet etkin; 128K bağlam |
| LLM — embedding | **text-embedding-3-small** (1536 boyut) | 3-large'dan ~8 kat ucuz; MVP için yeterli. **Bir kez seç, sonra sabitle** |
| Sunucu | Gunicorn (+ NGINX) | Docker Compose içinde |
| Şablon | Django Templates + Bootstrap 5 | HTMX (opsiyonel) ile kısmi güncellemeler |
| Test | pytest + pytest-django + factory_boy | Her fazda test yazılır |
| Kod kalitesi | Ruff, pre-commit | Lint + format + güvenlik taraması |

---

## 5. Önerilen Proje Yapısı

```
document_intelligence/          ← ana repo (git)
├── docker-compose.yml          (üretim: nginx+web+worker+beat+redis+db)
├── docker-compose.dev.yml      (geliştirme: db+redis yeterli)
├── .env.example
├── nginx/
│   └── nginx.conf / conf.d/default.conf
├── deploy/                     (CI/CD, backup betikleri)
└── src/
    ├── manage.py
    ├── config/                 (settings: base/dev/prod, celery.py, urls.py)
    └── apps/
        ├── accounts/           (User, roller, kayıt/giriş, profil)
        ├── documents/          (Document, DocumentChunk, yükleme, parsing)
        ├── ai_engine/          (embeddings, pgvector araması, RAG servisi)
        └── chat/               (function calling ajanı, sohbet arayüzü)
```

---

## 6. Fazlar — Yol Haritası

Her fazda **"Tanım: Tamamlandı" (Definition of Done)** listesi, o fazın bağımsız olarak doğrulanabilir şekilde kapandığının kanıtıdır. Sıra katman katman: önce zemin, sonra yetki, sonra veri, sonra işleme, sonra zeka.

---

### 💡 FAZ 0 — Ortam Kurulumu & Proje İskeleti (≈1 hafta)

**Amaç:** Herkese açık, çalışan, temiz bir Django projesi.

- Git repo + `.gitignore` + README + `LICENSE`
- `uv` / `venv` + `pyproject.toml` (bağımlılıklar pinli)
- Django 5.2 LTS projesi; `config/settings` üç ayraç (base / dev / prod)
- `.env` + `django-environ`; asla gerçek anahtar commit'lenmez
- **`accounts` uygulaması içinde custom User modeli** (email ile giriş) — ilk migration'dan önce!
- Ruff + pre-commit + git kancaları
- Bootstrap şablonu: base.html, navbar, flash mesajları

**DoD:** `python manage.py migrate` temiz çalışıyor; kurulum/yapılandırma adımları README'de; pre-commit çalışıyor.

---

### 🏗️ FAZ 1 — Altyapı Katmanı: Docker, PostgreSQL/pgvector, Redis (≈1 hafta)

**Amaç:** Tüm servisler yerelde tek komutla ayağa kalkar.

- `docker-compose.dev.yml`: `postgres:pg16+pgvector` + `redis:7`
- Django ↔ PostgreSQL bağlantısı (psycopg), bir test modeli üzerinde migration
- `pgvector` ekstansiyonu + ilk vektör migration denemesi (boş `embedding vector(1536)` kolonu olan bir model)
- Redis ayarları (cache backend + Celery broker URL)
- Sağlık kontrolü endpoint'i (`/healthz`) + compose healthcheck'ler

**DoD:** `docker compose up -d` → Django çalışıyor; `SELECT * FROM pg_extension` → `vector` mevcut; veritabanı bozulursa `docker compose down -v` ile sıfırlanabiliyor.

---

### 🔐 FAZ 2 — Kullanıcı, Kayıt/Giriş ve RBAC (≈1 hafta)

**Amaç:** Roller ve nesne sahipliği netleşsin; hiçbir özellik yetkisiz erişime açık olmasın.

- `django-allauth` ile kayıt / giriş / çıkış / şifre sıfırlama
- Roller: **admin** (her şey), **editor** (yükleme/silme), **viewer** (yalnızca okuma) — `User.role` + Groups
- Doküman sahipliği: `Document.owner` (FK) + `Document.is_public` bayrağı
- Decorator/mixin'ler: `@require_admin`, `OwnerOrReadOnly` vb.
- Arayüzde: profil sayfası, rol rozetleri

**DoD:** Üç ayrı hesapla test: viewer başkasının dokümanını görüntüleyemiyor; editor silebiliyor; admin her şeyi yapabiliyor. (pytest ile otomasyon)

---

### 📄 FAZ 3 — Doküman Modeli & Güvenli Yükleme (≈1 hafta)

**Amaç:** Dosyalar güvenle içeri girer ve yönetilebilir.

- `Document` modeli: dosya, başlık, tip, boyut, sahiplik, **durum makinesi** (yüklendi → işleniyor → hazır → hata)
- `DocumentChunk` modeli (şimdilik şema; FAZ 5'te doldurulur): text, embedding kolonu, metadata (sayfa no, başlık), indeks
- Dosya doğrulama: **magic bytes** ile gerçek tip kontrolü (uzantıya güvenme), boyut limiti (örn. 25 MB), dosya adı sanitize etme
- Upload formu + listeleme/silme/detay sayfaları (Bootstrap)
- Depolama: lokal media (prod'da S3'e taşınabilir)

**DoD:** PDF/zip/zip-bomb gibi kötü niyetli örnekler reddediliyor; dosya yüklenip listelenebiliyor; başkasının dosyası silinemez.

---

### ⚙️ FAZ 4 — Asenkron İşleme: Celery + Redis (≈1 hafta)

**Amaç:** Ağır iş artık web isteğini bloklamaz.

- Celery uygulaması (`config/celery.py`), `django-celery-beat`
- Görevler: `process_document` (orchestrator), ardından `parse_document`, `generate_embeddings` (alt adımlar FAZ 5–6'da dolar)
- Hata yönetimi: `autoretry_for` + exponential backoff, maksimum deneme sayısı, başarısız işte `Document.status = "error"` + hata mesajı
- İlerleme göstergesi: durum/ilerleme alanları doküman detay sayfasında
- Flower'ı dev ortamına ekle (kuyruk izleme)

**DoD:** Bir doküman yüklediğinde web anında yanıt veriyor, arka planda görev kuyrukta görünüyor; Redis durdurulursa görevler kuyrukta bekleyip Redis gelince işleniyor; başarısız görev "error" durumuna geçiyor.

---

### 🧩 FAZ 5 — Ayrıştırma (Parsing) & Parçalama (Chunking) (≈1–2 hafta)

**Amaç:** Her dosya türünden temiz, bağlamsal metin parçaları çıksın.

- **PDF:** PyMuPDF (metin + sayfa numarası; tablo bölgelerini işaretle)
- **Excel (.xlsx):** openpyxl — her sayfa/satır grubu ayrı parça; satır-meta verisi
- **CSV:** pandas/`csv` — başlık satırı korunur, makul satır blokları
- **TXT & Markdown (.md):** düz okuma; Markdown başlıkları (#) parça sınırı olarak kullan
- Normalizasyon: boşluk temizliği, Unicode normalizasyonu, fazla boş satırlar
- **Parçalayıcı:** recursive character splitter (langchain-text-splitters veya el yazımı), hedef ≈ 500–800 karakter, **%10 overlap**
- Parça başına metadata: `doc_id, chunk_index, page, section_heading`
- `tiktoken` ile token sayma (embedding maliyeti kestirimi için)

**DoD:** Depodaki 5 örnek dosya türünün her birinden anlamlı parçalar üretiliyor; her parçanın kaynağı (dosya + sayfa/bölüm) izlenebiliyor; parçalar DB'ye yazılıyor.

---

### 🔍 FAZ 6 — Embeddings & pgvector ile Semantik Arama (≈1–2 hafta)

**Amaç:** "anlam bazlı" arama çalışsın.

- OpenAI istemcisi (key .env'de; asla commit'leme)
- `text-embedding-3-small` ile **batch embedding** (örn. 64'lük gruplar, 429/rate-limit'e karşı backoff)
- `DocumentChunk.embedding` = `vector(1536)`; **HNSW indeks** (cosine)
- Arama servisi (`ai_engine`): soru → embedding → `<=>` cosine → top-k (örn. 8)
- **Hibrit arama (opsiyonel ama önerilir):** full-text search (PostgreSQL tsvector) + semantik → birleştir (RRF)
- **güvenlik:** sorgu, `Document.owner/is_public` yetkisine göre **mutlaka** filtrelenir
- Arama sayfası (template): sonuçlar dosya + sayfa/bölüm etiketiyle listelenir

**DoD:** Aynı kelimeleri içermeyen ama anlamsal olarak ilgili dokümanlar bulunuyor; kullanıcı yalnızca yetkili olduğu dokümanlarda sonuç alıyor; sorgu 1 sn altında.

---

### 🧠 FAZ 7 — Soru-Cevap & LLM Function Calling (≈2 hafta)

**Amaç:** "Belgelerimde X var mı?" sorularına **kaynak gösteren** cevaplar.

- Prompt sistemi: sistem mesajı + "yalnızca sağlanan bağlamdan cevapla; bulamazsan 'belgelerimde bu bilgi yok' de"
- RAG pipeline: soru → (FAZ 6 arama) → bağlam derleme (top-k parça; token bütçesi ~3–4K token) → gpt-4o-mini
- **Function calling döngüsü** (Özel ajan davranışı):
  - Fonksiyonlar: `search_documents(query, filters)`, `get_document_chunks(doc_id, page)`, `list_documents()`, `get_document_metadata(doc_id)`
  - LLM sorguyu analiz eder → ilgili fonksiyonu çağırır → sonucu kullanarak yanıtı yazar → en fazla 5 araç turu sonrası yanıt
  - Yetkiyi **LLM'e bırakma**: tüm fonksiyon çağrıları sunucuda kullanıcının rolüyle filtreli çalışır (kullanıcı yalnızca görebildiği dokümanlara erişir)
- **Kaynak gösterme:** yanıtın altında `[Kaynak: dosya.pdf, s.3]` çıktısı; geriye dönük parça ID'leri
- Sohbet arayüzü (template + HTMX isteğe bağlı): geçmiş, kopyalama
- Token/maliyet koruması: soru başına max token, kullanıcı başına rate-limit (Redis)
- A/b testi ayarı: "önce arama sonra cevap" + "ham LLM cevabı" karşılaştırması (değerlendirme için)

**DoD:** 10 soruluk altın sette yanıtlar bilgi dışı uydurma yapmıyor (uydurma olgusu "kaynak yok" ile cevaplanıyor); her yanıt kaynaklı; yetkisiz dokümana ait bilgi sızdırılmıyor.

---

### 🎨 FAZ 8 — Frontend: Django Templates (≈1–2 hafta)

**Amaç:** Platform kullanılabilir bir ürüne dönüşsün.

- Dashboard: son dokümanlar, istatistikler, işleme durumu
- Doküman detay: meta veri, parça sayısı, dönem/yerler, yeniden işleme butonu
- Semantik arama sayfası: gelişmiş filtreler (tarih, tip, sahiplik)
- **Sohbet sayfası:** konuşma arayüzü, kaynak kartları, örnek sorular
- HTMX ile: yükleme sonrası durum güncellemesi, sonuç sayfalaması
- Responsive Bootstrap; boş durum ekranları; hata sayfaları (403/404/500) özelleştirme

**DoD:** Üç farklı rol için akıcı bir "görev yolculuğu" (yükle → bekle → ara → sor) uçtan uca çalışıyor.

---

### ✅ 🧪 FAZ 9 — Test, Güvenlik & Performans (tamamlandı)

**Amaç:** Deploy edilebilir olgunluk.

- pytest: model, servis, görünüm, Celery görevleri testleri (factory_boy ile)
- **RAG değerlendirmesi:** altın soru seti; retrieval kalitesi (hit@k) + yanıt doğruluğu; gelişme ölçümü
- Güvenlik: `python manage.py check --deploy`; `SECURE_*` ayarları; CSRF; Content-Security-Policy; dosya boyutu/dosya tipi sınırlarının testleri; rate limiting
- Performans: DB indeksleri (owner, status, tsvector), sorgu sayısı (n+1) temizliği, Redis cache (doküman meta, arama önbelleği)
- Loglama (JSON) + hata izleme (Sentry opsiyonel)

**DoD:** `pytest` yeşil; check --deploy kritik uyarısı yok; doküman işleme ve arama talepleri kabul edilebilir sürelerde (kıyas öncesi/sonrası metrik).

---

### ✅ 🚀 FAZ 10 — Ready to Deploy (Üretime Hazırlık) (tamamlandı)

**Amaç:** Platform, öğrenim amaçlı geliştirildiğinden gerçek bir sunucuya
yayınlanmayacak; ancak **istenirse tek komutla üretim ortamına kurulabilecek**
olgunlukta bir kuruluma sahip olsun.

- `docker-compose.yml` (prod): `nginx` (TLS + statik) · `web` (Gunicorn, 2–4 worker) · `celery-worker` · `celery-beat` · `redis` · `db` (pgvector imajı)
- Let's Encrypt (certbot) ile SSL; HTTP→HTTPS yönlendirme (hazır template/config)
- `.env.prod` örneği: SECRET_KEY, DB, OpenAI, DEBUG=False, ALLOWED_HOSTS
- Yedekleme: `pg_dump` + media yedeği betikleri; geri yükleme talimatı
- CI/CD: GitHub Actions (lint + test + build), sağlık kontrolü
- İzleme: Flower (kuyruk), temel uptime kontrolü

**DoD:** `docker compose up -d --build` ile temiz bir makinede tek komutla
ayağa kalkabiliyor; TLS/config dosyaları hazır; yedek/geri yükleme betikleri
çalışıyor; CI'da otomatik test —gerçek bir sunucuya deploy zorunluluğu yok—.

---

## 7. Kritik Tasarım Kararları (En Baştan Doğru Yapılmalı)

1. **Custom User modeli ilk günden:** Varsayılan `auth.User` ile başlayıp sonra değiştirmek migration cehennemidir. Özel modeli Faz 0'da kurun.
2. **Embedding modelini sabitle:** `text-embedding-3-small` = 1536 boyut. Sorgu embedding'i ile saklanan vektörler **aynı model**den olmalı; ortası değiştirmek yeniden embedding (re-embed) gerektirir.
3. **Retrieval'da RBAC:** Arama sorgusuna kullanıcı yetkisi **sunucu tarafında** eklenir. LLM'den yetki kontrolü beklemeyin — prompt injection ve sızıntı kapısıdır.
4. **Parça boyutu sabit:** ~500–800 karakter + %10 overlap; tutarlılık hem arama kalitesini hem maliyeti belirler.
5. **Function calling yetki sınırı:** Araç çağrıları her zaman oturumdaki kullanıcı ile filtrelenir; `doc_id` doğrudan kullanıcıya ait değilse 404/403 döner.
6. **Dosya doğrulama:** Uzantıya asla güvenme — magic bytes + boyut limiti + dosya adı sanitizasyonu.
7. **Token bütçesi:** Bağlam ~3–4K token ile sınırlı; aksi halde uzun dokümanlarda maliyet patlar ve cevap kalitesi düşer.
8. **OpenAI rate limitleri:** Batch embedding + exponential backoff + Redis tabanlı kullanıcı limitleri (maliyet kontrolü için de şart).

---

## 8. MVP Kapsam Dışı (Sonraki Fazlara Bırak)

Bu maddeler ilk sürümde **bilerek** yapılmaz; temel akış sağlamlaştıktan sonra eklenir:

- OCR (taranmış PDF'ler) — önce metin tabanlı PDF'ler
- Multitenant/team yapısı — önce tek kullanıcı-sahipliği mimarisi
- Cross-encoder / re-ranking — önce top-k kaba arama
- Uzun doküman özetleme (map-reduce) — önce başı-sonu tutarlı parça araması
- Dosya kilitleri / versiyon geçmişi — önce basit üzerine yazma
- S3 / bulut depolama — önce lokal media (aynı arayüzle geçiş kolay)
- SSO / LDAP — önce email-şifre girişi
- Audit log / SIEM entegrasyonu — önce temel loglama
- Video/audio transkript işleme — kapsam dışı (yalnızca belirtilen 5 dosya tipi)

---

## 9. Zaman Çizelgesi Özeti

| Faz | İçerik | Part-time (akşam/hafta sonu) | Full-time |
|---|---|---|---|
| 0 | Ortam & iskelet | 1 hafta | 1 gün |
| 1 | Docker/DB/Redis | 1 hafta | 1–2 gün |
| 2 | Auth & RBAC | 1 hafta | 1–2 gün |
| 3 | Doküman & yükleme | 1 hafta | 1–2 gün |
| 4 | Celery/Redis | 1 hafta | 1–2 gün |
| 5 | Parsing & chunking | 1–2 hafta | 2–3 gün |
| 6 | Embeddings & arama | 1–2 hafta | 2–3 gün |
| 7 | LLM QA & function calling | 2 hafta | 3–4 gün | ✅ |
| 8 | Frontend templates | 1–2 hafta | 2–3 gün |
| 9 | Test/güvenlik/perf | 1–2 hafta | 2–3 gün |
| 10 | Production deploy | 1 hafta | 1–2 gün |
| | **Toplam** | **≈ 11–15 hafta** | **≈ 4–6 hafta** |

**Milestone noktaları (kutlama anları):** Faz 4 sonu = "ilk dosya kuyrukta işlendi" · Faz 6 sonu = "ilk semantik arama çalıştı" · Faz 7 sonu = "ilk kaynak gösteren cevap alındı" · Faz 10 sonu = "üretime hazır kurulum tamam".

---

## 10. Kaynaklar

- PostgreSQL: https://www.postgresql.org/docs/current/ · pgvector: https://github.com/pgvector/pgvector
- Django 5.2 LTS: https://docs.djangoproject.com/en/5.2/ · Custom User: https://docs.djangoproject.com/en/5.2/topics/auth/customizing/
- django-allauth: https://docs.allauth.org/
- Celery: https://docs.celeryq.dev/ · django-celery-beat: https://github.com/celery/django-celery-beat
- OpenAI: Function calling https://platform.openai.com/docs/guides/function-calling · Embeddings https://platform.openai.com/docs/guides/embeddings · Token sayma: https://github.com/openai/tiktoken
- langchain-text-splitters: https://python.langchain.com/docs/integrations/text_splitters/
- Docker Compose: https://docs.docker.com/compose/ · Gunicorn: https://docs.gunicorn.org/ · NGINX: https://nginx.org/en/docs/
- HTMX: https://htmx.org/ (opsiyonel)
