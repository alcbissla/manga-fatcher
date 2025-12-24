import os
import time
import cloudscraper
from bs4 import BeautifulSoup
from PIL import Image
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN") or "PUT_BOT_TOKEN_HERE"
BASE_DIR = "downloads"
MAX_RETRIES = 3
TIMEOUT = 20
# ============================================

os.makedirs(BASE_DIR, exist_ok=True)

scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "desktop": True}
)

# ================== HTTP ==================
def safe_get(url):
    for _ in range(MAX_RETRIES):
        try:
            r = scraper.get(url, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.text
        except:
            time.sleep(2)
    return None

# ================== SITE PRESETS ==================

def chapters_mangadex(url):
    html = safe_get(url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    return [a["href"] for a in soup.select("a[href*='/chapter/']")]

def chapters_mangasee(url):
    html = safe_get(url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    return [a["href"] for a in soup.select("div.chapter-list a")]

def chapters_asura(url):
    html = safe_get(url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    return [a["href"] for a in soup.select("ul.main li a")]

def chapters_reaper(url):
    html = safe_get(url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    return [a["href"] for a in soup.select("div.wp-manga-chapter a")]

def chapters_manhwaread(url):
    html = safe_get(url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    return [a["href"] for a in soup.select("ul.chapter-list li a")]

def detect_site(url):
    if "mangadex" in url:
        return chapters_mangadex
    if "mangasee" in url:
        return chapters_mangasee
    if "asura" in url:
        return chapters_asura
    if "reaper" in url:
        return chapters_reaper
    if "manhwaread" in url:
        return chapters_manhwaread
    return None

# ================== IMAGES ==================

def get_images(chapter_url):
    html = safe_get(chapter_url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")

    selectors = [
        "img.chapter-img",
        "img.img-responsive",
        "img.wp-manga-chapter-img",
        "img"
    ]

    images = []
    for sel in selectors:
        for img in soup.select(sel):
            src = img.get("src")
            if src and src.startswith("http"):
                images.append(src)
        if images:
            break

    return images

def download_images(urls, folder, progress_cb=None):
    paths = []
    total = len(urls)

    for i, url in enumerate(urls, 1):
        try:
            data = scraper.get(url, timeout=TIMEOUT).content
            path = os.path.join(folder, f"{i:03}.jpg")
            with open(path, "wb") as f:
                f.write(data)
            paths.append(path)

            if progress_cb:
                progress_cb(i, total)
        except:
            continue

    return paths

def images_to_pdf(images, pdf_path):
    if not images:
        return False

    pages = []
    for img in images:
        try:
            pages.append(Image.open(img).convert("RGB"))
        except:
            pass

    if not pages:
        return False

    pages[0].save(pdf_path, save_all=True, append_images=pages[1:])
    return True

# ================== TELEGRAM ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 Manga Downloader Bot\n\n"
        "Supported:\n"
        "- MangaDex\n"
        "- MangaSee\n"
        "- Asura Scans\n"
        "- Reaper Scans\n"
        "- Manhwaread.com\n\n"
        "Send the *FIRST CHAPTER LINK*.",
        parse_mode="Markdown"
    )

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    parser = detect_site(url)

    if not parser:
        await update.message.reply_text("❌ Unsupported site.")
        return

    status = await update.message.reply_text("🔍 Fetching chapters...")
    chapters = parser(url)

    if not chapters:
        await status.edit_text("❌ No chapters found.")
        return

    chapters = list(dict.fromkeys(chapters))
    total_chapters = len(chapters)

    await status.edit_text(f"📚 Found {total_chapters} chapters.")

    for idx, chapter_url in enumerate(chapters, 1):
        chapter_dir = os.path.join(BASE_DIR, f"chapter_{idx}")
        os.makedirs(chapter_dir, exist_ok=True)

        progress_msg = await update.message.reply_text(
            f"⬇️ Chapter {idx}/{total_chapters}\nPreparing..."
        )

        images = get_images(chapter_url)
        if not images:
            await progress_msg.edit_text("⚠️ No images, skipped.")
            continue

        def progress(done, total):
            try:
                context.application.create_task(
                    progress_msg.edit_text(
                        f"⬇️ Chapter {idx}/{total_chapters}\n"
                        f"Pages: {done}/{total}"
                    )
                )
            except:
                pass

        image_files = download_images(images, chapter_dir, progress)

        pdf_path = os.path.join(BASE_DIR, f"Chapter_{idx}.pdf")
        success = images_to_pdf(image_files, pdf_path)

        if success:
            await progress_msg.edit_text(f"📄 Sending Chapter {idx}")
            await update.message.reply_document(open(pdf_path, "rb"))
        else:
            await progress_msg.edit_text("❌ PDF failed.")

    await update.message.reply_text("✅ All chapters completed.")

# ================== RUN ==================

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))

print("Bot running...")
app.run_polling()
