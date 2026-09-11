# 📸 Telegram Personal Instagram Media Downloader Bot
### ربات تلگرام دانلود و ارسال خودکار مدیاهای اینستاگرام به صورت اختصاصی و امن

---

[English Documentation](#english-documentation) | [راهنمای فارسی](#راهنمای-فارسی)

---

<a name="english-documentation"></a>
# 🇬🇧 English Documentation

## 1. Project Overview
A production-ready, asynchronous personal Telegram bot designed to download and deliver authorized media from Instagram (Posts, Reels, Carousels, and Stories) directly into your private Telegram chat.

### Key Capabilities:
- **Private & Single-User / Multi-Admin Access**: Restricted strictly to authorized Telegram User IDs.
- **Full Media Support**: Single photos, single videos (Reels/IGTV), multi-image/video albums (Carousels as Telegram Media Groups), and Stories.
- **Dual Ingestion Channels**:
  1. Direct Telegram paste: Send any Instagram link directly to the bot.
  2. Instagram DM Forwarding: Send links to your controlled Instagram account via DM, received via Meta Webhooks.
- **Strict Compliance & Security**: No scraping of credentials, no session-cookie theft, and no anti-bot circumvention. Operates via official Meta Graph API, oEmbed, and Webhook interfaces.
- **Duplicate Prevention**: SQLite database tracks processing status (`PENDING`, `DOWNLOADING`, `DOWNLOADED`, `SENT`, `FAILED`) to avoid re-downloading identical media.
- **Safe Temporary Storage**: Streaming downloads with integrity verification and automatic post-delivery file deletion.
- **Telegram Limit Guards**: Automatically respects Telegram's 50 MB upload limits for bots.

---

## 2. Architecture

```
                                  +-----------------------------+
                                  |    Instagram User Input     |
                                  |  (Direct Message or Chat)   |
                                  +--------------+--------------+
                                                 |
                                                 v
                                  +-----------------------------+
                                  |  Meta Webhook / Poller or   |
                                  |     Telegram Bot Listener   |
                                  +--------------+--------------+
                                                 |
                                                 v
                                  +-----------------------------+
                                  |    Authorization Gate       |
                                  |  (AUTHORIZED_TELEGRAM_IDS)  |
                                  +--------------+--------------+
                                                 |
                                                 v
                                  +-----------------------------+
                                  |      URL Parsing & Check    |
                                  |   (Duplicate Check in DB)   |
                                  +--------------+--------------+
                                                 |
                        +------------------------+------------------------+
                        |                                                 |
                        v                                                 v
             [ Already Processed ]                             [ New / Pending Media ]
                        |                                                 |
                        v                                                 v
             Notify Telegram User                              Resolve Media Stream
                                                          (Meta Graph API / oEmbed)
                                                                          |
                                                                          v
                                                               Download to downloads/
                                                              (Chunked, Max 50MB Cap)
                                                                          |
                                                                          v
                                                               Validate Magic Bytes
                                                              (JPEG, PNG, MP4, WebM)
                                                                          |
                                                                          v
                                                              Deliver to Telegram Chat
                                                          (Photo, Video, or MediaGroup)
                                                                          |
                                                                          v
                                                              Record Status -> SENT
                                                                          |
                                                                          v
                                                              Delete Temporary Files
```

---

## 3. Creating Your Telegram Bot
1. Open Telegram and message [@BotFather](https://t.me/BotFather).
2. Send the command `/newbot`.
3. Choose a display name (e.g., `My Media Bot`) and a username ending in `bot` (e.g., `my_insta_dl_bot`).
4. Copy the HTTP API token provided (e.g., `123456789:ABCdefGHIjklMNOpqrSTUvwxYZ`). This is your `TELEGRAM_BOT_TOKEN`.
5. Find your personal Telegram numerical ID:
   - Message [@userinfobot](https://t.me/userinfobot) or [@raw_data_bot](https://t.me/raw_data_bot).
   - Copy your `Id` (e.g., `123456789`). This is your `AUTHORIZED_TELEGRAM_USER_IDS`.

---

## 4. Configuration Reference

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Edit `.env` with your settings:

| Variable | Description | Default | Example |
| :--- | :--- | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | Bot API token from @BotFather | *(Required)* | `123456:ABC...` |
| `AUTHORIZED_TELEGRAM_USER_IDS`| Comma-separated list of allowed user IDs | *(Required)* | `123456789,987654321` |
| `INSTAGRAM_ACCOUNT` | Your controlled Instagram username | `""` | `my_creator_account` |
| `INSTAGRAM_AUTH_METHOD` | `graph_api`, `oembed`, `webhook`, or `mock` | `graph_api` | `graph_api` |
| `INSTAGRAM_ACCESS_TOKEN` | Meta Graph API user or page token | `""` | `EAAB...` |
| `INSTAGRAM_APP_SECRET` | App Secret from Meta Developer Dashboard | `""` | `0123456789abcdef` |
| `INSTAGRAM_VERIFY_TOKEN` | Custom string for Webhook challenge verification | `""` | `my_secret_token_123` |
| `DATABASE_URL` | SQLite database file location | `sqlite:///data/bot.db` | `sqlite:///data/bot.db` |
| `DOWNLOAD_DIR` | Directory for temporary files | `./downloads` | `./downloads` |
| `KEEP_DOWNLOADS` | Keep media files after sending | `false` | `false` |
| `MAX_DOWNLOAD_SIZE_BYTES` | Max download and delivery file size | `52428800` (50MB) | `52428800` |
| `MAX_RETRIES` | Max transient download retries | `3` | `3` |
| `WEBHOOK_PORT` | Port for Meta Webhook listener | `8000` | `8000` |
| `LOG_LEVEL` | Logging verbosity | `INFO` | `INFO` |

---

## 5. Instagram Authentication & Integration Requirements

### Official Meta Developer Integration:
1. **Account Type**: The controlled Instagram account must be a **Professional (Creator or Business)** account.
2. **Meta Developer App**:
   - Create an app on [developers.facebook.com](https://developers.facebook.com/).
   - Select "Other" -> "Business".
   - Add the **Instagram Graph API** and **Messenger API for Instagram** products.
3. **Permissions**:
   - `instagram_basic`: Required to read public media and metadata.
   - `instagram_manage_messages`: Required to receive incoming Direct Messages via Webhook.
4. **Webhooks Setup**:
   - Callback URL: `https://your-domain.com/webhook/instagram`
   - Verify Token: Matches your `INSTAGRAM_VERIFY_TOKEN`.
   - Field Subscriptions: `messages`.

### For Personal Accounts & Offline Testing:
- Meta does not offer official Direct Message webhooks for standard personal non-business accounts without converting to a Creator account.
- You can directly paste any Instagram link into the Telegram bot chat.
- Set `INSTAGRAM_AUTH_METHOD=mock` to run offline tests or dry runs without needing active Meta API credentials.

---

## 6. Running Locally (Step-by-Step for Beginners)

### Prerequisites:
- Python 3.11 or 3.12 installed.

### Steps:
```bash
# 1. Clone or navigate to the project directory
cd /path/to/project

# 2. Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install required packages
pip install -r requirements.txt

# 4. Create your configuration file
cp .env.example .env
nano .env   # Enter your TELEGRAM_BOT_TOKEN and AUTHORIZED_TELEGRAM_USER_IDS

# 5. Run the bot
python -m app.main
```

---

## 7. Running with Docker & Docker Compose

Docker ensures the bot runs isolated with persistent data storage:

```bash
# 1. Ensure your .env file is prepared
cp .env.example .env
# edit .env with your values

# 2. Start container in detached background mode
docker compose up -d

# 3. Inspect live logs
docker compose logs -f

# 4. Stop container
docker compose down
```

---

## 8. Running Automated Tests

Run the full automated test suite (29 tests verifying URL parsing, authorization, database storage, magic bytes, size limits, Telegram sender, and Webhooks):

```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

---

## 9. Troubleshooting & Common Issues

| Issue | Cause | Solution |
| :--- | :--- | :--- |
| `Access Denied` message in Telegram | Your Telegram ID is not in `AUTHORIZED_TELEGRAM_USER_IDS` | Check your ID with `@userinfobot` and add it to `.env` |
| `File Size Limit Exceeded` (50MB) | Video exceeds Telegram Bot API upload threshold | Bot will notify you with the direct link; bots cannot send files > 50MB |
| `Post has been deleted` or 404 | Original creator removed the post | Verify that the URL opens in a web browser |
| `Private account requires authorization` | Post is from a private profile | Provide an authenticated `INSTAGRAM_ACCESS_TOKEN` with access permissions |
| Webhook challenge fails | `INSTAGRAM_VERIFY_TOKEN` mismatch | Verify matching strings in Meta Developer App and `.env` |

---

<a name="راهنمای-فارسی"></a>
# 🇮🇷 راهنمای فارسی

## ۱. معرفی پروژه
این پروژه یک ربات تلگرام شخصی، ناهمگام (Asynchronous) و آماده استفاده در محیط پروداکشن به زبان پایتون است که لینک‌های اینستاگرام (پست، ریلز، استوری و آلبوم‌های چندتایی یا کاروسل) را اعتبارسنجی کرده، مدیا را با رعایت کامل الزامات امنیتی دانلود نموده و مستقیماً به چت خصوصی تلگرام شما ارسال می‌کند.

### ویژگی‌های اصلی:
- **دسترسی کاملاً اختصاصی**: فقط شناسه‌های کاربری تلگرام مجاز (`AUTHORIZED_TELEGRAM_USER_IDS`) می‌توانند از ربات استفاده کنند.
- **پشتیبانی کامل از انواع رسانه**:
  - تصاویر تک فایلی (`sendPhoto`)
  - ویدیوها و ریلز (`sendVideo`)
  - آلبوم‌های اسلایدی کاروسل (`sendMediaGroup` به صورت آلبوم یکپارچه)
  - استوری‌ها (در صورت معتبر بودن و منقضی نشدن زمان ۲۴ ساعته)
- **دو روش دریافت ورودی**:
  1. ارسال مستقیم لینک اینستاگرام به چت ربات تلگرام.
  2. دایرکت دادن لینک به اکانت اینستاگرام تحت کنترل خودتان (از طریق وب‌هوک رسمی متا).
- **امنیت بالا و رعایت قوانین**: عدم ذخیره پسورد اینستاگرام، عدم سرقت کوکی‌های نشست، و عدم استفاده از روش‌های ناامن کرک کپچا.
- **جلوگیری هوشمند از پردازش تکراری**: رهگیری وضعیت هر رسانه در پایگاه داده SQLite.
- **پاکسازی خودکار حافظه**: فایل‌های دانلود شده پس از تحویل به تلگرام بلافاصله از روی سرور حذف می‌شوند تا فضای دیسک پر نشود.
- **کنترل محدودیت حجم تلگرام**: فایل‌های بالای ۵۰ مگابایت به صورت شفاف به کاربر گزارش می‌شوند تا ربات با خطا متوقف نشود.

---

## ۲. راهنمای گام به گام ساخت ربات تلگرام
اگر تا به حال ربات تلگرام نساخته‌اید، مراحل زیر را طی کنید:
1. در تلگرام وارد ربات رسمی [@BotFather](https://t.me/BotFather) شوید.
2. دستور `/newbot` را ارسال کنید.
3. یک نام دلخواه (مثلاً `My Personal Downloader`) و یک نام کاربری که با `bot` تمام شود (مثلاً `alireza_instadl_bot`) انتخاب کنید.
4. توکن API دریافتی را کپی کنید. این مقدار همان `TELEGRAM_BOT_TOKEN` است.
5. برای به دست آوردن آیدی عددی تلگرام خود، به ربات [@userinfobot](https://t.me/userinfobot) پیام دهید و عدد `Id` را کپی کنید. این مقدار همان `AUTHORIZED_TELEGRAM_USER_IDS` است.

---

## ۳. تنظیمات و متغیرهای محیطی
یک کپی از فایل نمونه ایجاد کنید:
```bash
cp .env.example .env
```
سپس فایل `.env` را با ویرایشگر دلخواه خود ویرایش کنید:
```ini
# توکن ربات تلگرام
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ

# آیدی عددی اکانت تلگرام شما (برای چند نفر با ویرگول جدا کنید)
AUTHORIZED_TELEGRAM_USER_IDS=123456789

# نام کاربری اینستاگرام شما
INSTAGRAM_ACCOUNT=my_account

# روش احراز هویت (graph_api برای استفاده واقعی، mock برای تست)
INSTAGRAM_AUTH_METHOD=graph_api
```

---

## ۴. نحوه اجرای پروژه

### الف) اجرای مستقیم در سیستم (Local):
```bash
# ایجاد محیط ایزوله پایتون
python3 -m venv venv
source venv/bin/activate

# نصب کتابخانه‌های مورد نیاز
pip install -r requirements.txt

# اجرای برنامه
python -m app.main
```

### ب) اجرا با داکر (Docker Compose):
```bash
# اجرا در پس‌زمینه
docker compose up -d

# مشاهده لاگ‌ها
docker compose logs -f

# خاموش کردن کانتینر
docker compose down
```

---

## ۵. اجرای تست‌های خودکار
برای اطمینان از سلامت تمام بخش‌های سیستم:
```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

---

## ۶. محدودیت‌های شناخته‌شده و توصیه‌های آتی
1. **محدودیت رسمی اینستاگرام برای اکانت‌های شخصی**: متا وب‌هوک پیام دایرکت را فقط برای اکانت‌های تجاری (Business) و سازنده محتوا (Creator) متصل به فیسبوک ارائه می‌دهد. برای اکانت‌های عادی شخصی، ساده‌ترین و پایدارترین روش ارسال مستقیم لینک به ربات تلگرام است.
2. **سقف حجم ربات‌های تلگرام**: ربات‌های تلگرام به صورت پیش‌فرض نمی‌توانند فایل‌های بزرگتر از ۵۰ مگابایت را آپلود کنند. این سامانه قبل از آپلود حجم را بررسی کرده و در صورت رد شدن، پیام هشدار شفاف همراه با لینک مستقیم به شما نمایش می‌دهد.
3. **توسعه‌های آینده**:
   - افزودن امکان فشرده‌سازی خودکار ویدیوهای بالای ۵۰ مگابایت با FFmpeg.
   - اضافه کردن دکمه‌های شیشه‌ای (Inline Buttons) برای انتخاب کیفیت ویدیو (۱۰۸۰p، ۷۲۰p یا فقط صدا).
