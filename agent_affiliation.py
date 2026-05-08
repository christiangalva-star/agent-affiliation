#!/usr/bin/env python3
"""
Agent ShopForYou V2
===================
- Scan Amazon multi-niches (5-60€)
- Mise à jour boutique GitHub Pages
- Post automatique Instagram
- Génération vidéo TikTok
- Scheduler quotidien
"""
import os
import re
import time
import json
import random
import logging
import schedule
import requests
import tempfile
import base64
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass, asdict
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("shopforyou")

# ── CONFIG ─────────────────────────────────────────────────────────────────────
AMAZON_TAG        = os.getenv("AMAZON_TAG", "shopforyou099-21")
GITHUB_TOKEN      = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO       = os.getenv("GITHUB_REPO", "christiangalva-star/agent-affiliation")
INSTAGRAM_TOKEN   = os.getenv("INSTAGRAM_TOKEN", "")
INSTAGRAM_ACCOUNT = os.getenv("INSTAGRAM_ACCOUNT_ID", "")
TIKTOK_SESSION_ID  = os.getenv("TIKTOK_SESSION_ID", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

MIN_PRICE         = float(os.getenv("MIN_PRICE", "5.0"))
MAX_PRICE         = float(os.getenv("MAX_PRICE", "60.0"))
MIN_RATING        = float(os.getenv("MIN_RATING", "4.0"))
MIN_REVIEWS       = int(os.getenv("MIN_REVIEWS", "50"))
PRODUCTS_PER_DAY  = int(os.getenv("PRODUCTS_PER_DAY", "3"))
PUBLISH_HOUR      = os.getenv("PUBLISH_HOUR", "09:00")

# Niches multi-catégories
NICHES = [
    {"query": "chaussettes fantaisie humour",       "category": "mode",     "emoji": "🧦"},
    {"query": "lunettes soleil tendance femme",      "category": "mode",     "emoji": "🕶️"},
    {"query": "bijoux fantaisie tendance",           "category": "mode",     "emoji": "💍"},
    {"query": "sac main femme tendance",             "category": "mode",     "emoji": "👜"},
    {"query": "bougie parfumée maison",              "category": "maison",   "emoji": "🕯️"},
    {"query": "organisateur bureau rangement",       "category": "maison",   "emoji": "🗂️"},
    {"query": "coussin décoratif salon",             "category": "maison",   "emoji": "🛋️"},
    {"query": "plante artificielle décorative",      "category": "maison",   "emoji": "🪴"},
    {"query": "sérum visage anti-âge",               "category": "beaute",   "emoji": "✨"},
    {"query": "masque cheveux nourrissant",          "category": "beaute",   "emoji": "💆"},
    {"query": "huile corps hydratante",              "category": "beaute",   "emoji": "🧴"},
    {"query": "brosse maquillage professionnel",     "category": "beaute",   "emoji": "💄"},
    {"query": "gadget cuisine original",             "category": "cuisine",  "emoji": "🍳"},
    {"query": "thermos café inox",                   "category": "cuisine",  "emoji": "☕"},
    {"query": "accessoire yoga fitness",             "category": "bienetre", "emoji": "🧘"},
    {"query": "diffuseur huiles essentielles",       "category": "bienetre", "emoji": "🌿"},
]

CAT_LABELS = {
    "mode":     "Mode",
    "maison":   "Maison",
    "beaute":   "Beauté",
    "cuisine":  "Cuisine",
    "bienetre": "Bien-être",
}

HOOKS = [
    "Stop scrolling, tu DOIS voir ça 👀",
    "Ce produit va changer ta routine 🔥",
    "La trouvaille de la semaine 😍",
    "Tout le monde en parle en ce moment...",
    "J'ai testé et c'est incroyable ✨",
    "Le cadeau parfait à moins de {price}€ 🎁",
    "Moins de {price}€ et c'est ouf 🤯",
    "Comment j'ai découvert ça ? 👇",
]

# ── DATACLASS ──────────────────────────────────────────────────────────────────
@dataclass
class Product:
    title: str
    price: float
    rating: float
    reviews: int
    asin: str
    affiliate_url: str
    image_url: str
    category: str
    emoji: str
    score: float = 0.0

# ── MODULE 1 : SCANNER AMAZON ──────────────────────────────────────────────────
class AmazonScanner:
    BASE = "https://www.amazon.fr/s"

    def fetch(self, url: str) -> Optional[str]:
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox"]
                )
                ctx = browser.new_context(
                    locale="fr-FR",
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/120.0.0.0 Safari/537.36"
                )
                page = ctx.new_page()
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                time.sleep(random.uniform(2, 4))
                html = page.content()
                browser.close()
            return html
        except Exception as e:
            log.warning(f"Fetch error {url}: {e}")
            return None

    def parse(self, html: str, niche: dict) -> List[Product]:
        soup = BeautifulSoup(html, "html.parser")
        products = []
        for item in soup.select('[data-component-type="s-search-result"]'):
            try:
                title_el = item.select_one("h2 a span")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)

                link_el = item.select_one("h2 a")
                path = link_el.get("href", "") if link_el else ""
                asin = path.split("/dp/")[1].split("/")[0] if "/dp/" in path else ""
                if not asin:
                    continue

                price_el = item.select_one(".a-price .a-offscreen")
                if not price_el:
                    continue
                price_txt = price_el.get_text(strip=True).replace(" ", "").replace(",", ".").replace("€", "").replace("EUR", "")
                price = float("".join(c for c in price_txt if c.isdigit() or c == ".") or 0)
                if not (MIN_PRICE <= price <= MAX_PRICE):
                    continue

                rating_el = item.select_one(".a-icon-alt")
                rating_txt = rating_el.get_text(strip=True).split(" ")[0].replace(",", ".") if rating_el else "0"
                rating = float(rating_txt or 0)
                if rating < MIN_RATING:
                    continue

                reviews_el = item.select_one(".a-size-base.s-underline-text")
                reviews_txt = reviews_el.get_text(strip=True).replace(" ", "").replace("\xa0", "").replace(",", "") if reviews_el else "0"
                reviews = int("".join(c for c in reviews_txt if c.isdigit()) or 0)
                if reviews < MIN_REVIEWS:
                    continue

                img_el = item.select_one("img.s-image")
                image_url = img_el.get("src", "") if img_el else ""

                affiliate_url = f"https://www.amazon.fr/dp/{asin}?tag={AMAZON_TAG}"

                import math
                score = (rating * 20) + (math.log10(reviews + 1) * 15) + max(0, (1 - price / MAX_PRICE) * 10)

                products.append(Product(
                    title=title, price=price, rating=rating, reviews=reviews,
                    asin=asin, affiliate_url=affiliate_url, image_url=image_url,
                    category=niche["category"], emoji=niche["emoji"], score=round(score, 2)
                ))
            except Exception:
                continue
        return products

    def scan(self) -> List[Product]:
        all_products = []
        niches = random.sample(NICHES, min(6, len(NICHES)))
        for niche in niches:
            url = f"{self.BASE}?k={requests.utils.quote(niche['query'])}&s=review-rank"
            log.info(f"Scan: {niche['query']}")
            html = self.fetch(url)
            if html:
                products = self.parse(html, niche)
                all_products.extend(products)
            time.sleep(random.uniform(3, 6))

        all_products.sort(key=lambda x: x.score, reverse=True)
        seen_asins = set()
        unique = []
        for p in all_products:
            if p.asin not in seen_asins:
                seen_asins.add(p.asin)
                unique.append(p)

        log.info(f"Produits trouvés : {len(unique)}")
        return unique[:PRODUCTS_PER_DAY]

# ── MODULE 2 : MISE À JOUR BOUTIQUE ────────────────────────────────────────────
class ShopUpdater:
    """Met à jour index.html sur GitHub Pages via l'API GitHub."""
    API = "https://api.github.com"

    def __init__(self):
        self.headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }

    def get_file(self):
        r = requests.get(f"{self.API}/repos/{GITHUB_REPO}/contents/index.html", headers=self.headers)
        r.raise_for_status()
        data = r.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        sha = data["sha"]
        return content, sha

    def build_card(self, p: Product) -> str:
        stars = "★" * int(p.rating) + "☆" * (5 - int(p.rating))
        cat_label = CAT_LABELS.get(p.category, p.category.capitalize())
        title_short = p.title[:60] + "..." if len(p.title) > 60 else p.title
        return f'''
    <div class="card" data-cat="{p.category}">
      <div class="card-img-wrap">
        <div class="card-img">{p.emoji}</div>
      </div>
      <div class="card-body">
        <span class="card-category">{cat_label}</span>
        <p class="card-title">{title_short}</p>
        <div class="card-meta">
          <span class="stars">{stars}</span>
          <span class="reviews">{p.rating} · {p.reviews} avis</span>
        </div>
        <div class="card-footer">
          <div><div class="price">{p.price:.2f}€</div></div>
          <a href="{p.affiliate_url}" class="btn-voir" target="_blank">Voir →</a>
        </div>
      </div>
    </div>'''

    def update(self, products: List[Product]) -> bool:
        if not GITHUB_TOKEN:
            log.warning("GITHUB_TOKEN manquant — boutique non mise à jour")
            return False
        try:
            content, sha = self.get_file()
            new_cards = "\n".join(self.build_card(p) for p in products)
            marker_start = "<!-- PRODUITS_AUTO_START -->"
            marker_end = "<!-- PRODUITS_AUTO_END -->"
            if marker_start in content:
                pattern = f"{marker_start}.*?{marker_end}"
                replacement = f"{marker_start}\n{new_cards}\n    {marker_end}"
                new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
            else:
                new_content = content.replace(
                    '<div class="grid" id="grid">',
                    f'<div class="grid" id="grid">\n    {marker_start}\n{new_cards}\n    {marker_end}'
                )
            encoded = base64.b64encode(new_content.encode("utf-8")).decode("utf-8")
            payload = {
                "message": f"[Auto] {len(products)} nouveaux produits — {datetime.now().strftime('%d/%m/%Y')}",
                "content": encoded,
                "sha": sha
            }
            r = requests.put(
                f"{self.API}/repos/{GITHUB_REPO}/contents/index.html",
                headers=self.headers,
                json=payload
            )
            r.raise_for_status()
            log.info(f"✅ Boutique mise à jour avec {len(products)} produits")
            return True
        except Exception as e:
            log.error(f"Erreur mise à jour boutique : {e}")
            return False

# ── MODULE 3 : GÉNÉRATION IMAGE IA ────────────────────────────────────────────
class ImageGenerator:
    """Génère des images lifestyle via Replicate (Stable Diffusion)."""

    REPLICATE_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")

    PROMPTS = {
        "mode":     "elegant young woman wearing {product}, lifestyle photo, neutral background, professional fashion photography, soft lighting, high quality",
        "maison":   "{product} in a modern bright living room, interior design photo, cozy atmosphere, professional photography",
        "beaute":   "beautiful woman using {product}, spa atmosphere, soft lighting, beauty photography, professional",
        "cuisine":  "{product} in a modern kitchen, food photography style, bright lighting, professional",
        "bienetre": "person using {product}, zen atmosphere, wellness lifestyle photo, soft natural lighting",
        "default":  "{product} product showcase, lifestyle photography, professional, high quality",
    }

    def generate(self, product_title: str, category: str) -> str | None:
        if not self.REPLICATE_TOKEN:
            log.warning("REPLICATE_API_TOKEN manquant")
            return None
        log.info(f"Génération image IA pour : {product_title[:40]}")
        try:
            prompt_template = self.PROMPTS.get(category, self.PROMPTS["default"])
            product_short = product_title[:50]
            prompt = prompt_template.replace("{product}", product_short)
            prompt += ", 9:16 vertical format, instagram story style"

            # Lancer la génération
            r = requests.post(
                "https://api.replicate.com/v1/predictions",
                headers={
                    "Authorization": f"Token {self.REPLICATE_TOKEN}",
                    "Content-Type": "application/json"
                },
                json={
                    "version": "5f24084160c9089501c1b3545d9be3c27883ae2239b6f412990e82d4a6210f8",
                    "input": {
                        "prompt": prompt,
                        "width": 768,
                        "height": 1344,
                        "num_outputs": 1,
                    }
                }
            )
            r.raise_for_status()
            prediction = r.json()
            prediction_id = prediction["id"]

            # Attendre le résultat (max 60s)
            for _ in range(30):
                time.sleep(3)
                r2 = requests.get(
                    f"https://api.replicate.com/v1/predictions/{prediction_id}",
                    headers={"Authorization": f"Token {self.REPLICATE_TOKEN}"}
                )
                data = r2.json()
                if data["status"] == "succeeded":
                    image_url = data["output"][0]
                    log.info(f"✅ Image IA générée : {image_url}")
                    return image_url
                elif data["status"] == "failed":
                    log.error("Génération image IA échouée")
                    return None

        except Exception as e:
            log.error(f"Erreur Replicate détaillée : {type(e).__name__} — {e}")
            return None


# ── MODULE 4 : NOTIFICATION TELEGRAM ─────────────────────────────────────────
class TelegramNotifier:
    """Envoie les posts sur Telegram pour publication manuelle."""

    API = "https://api.telegram.org"

    def send_product(self, product, hook: str, ai_image_url: str = None) -> bool:
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            log.warning("Telegram non configuré")
            return False
        try:
            caption = (
                f"🎯 <b>STORY PRÊTE À POSTER</b>\n\n"
                f"{hook}\n\n"
                f"✨ {product.title[:80]}\n"
                f"⭐ {product.rating}/5 · {product.reviews} avis\n"
                f"💶 {product.price:.2f}€\n\n"
                f"🔗 {product.affiliate_url}\n\n"
                f"📲 <b>Caption Instagram/TikTok :</b>\n"
                f"{hook}\n"
                f"{product.emoji} {product.title[:60]}\n"
                f"⭐ {product.rating}/5 · {product.reviews} avis\n"
                f"💶 {product.price:.2f}€ seulement\n"
                f"👉 shopforyou31.fr\n\n"
                f"#shopforyou #{product.category} #bonplan #tendance #shopping #lifestyle"
            )

            image_to_send = ai_image_url or (product.image_url if product.image_url else None)

            if image_to_send:
                try:
                    # Télécharger l'image d'abord
                    import urllib.request
                    img_data = urllib.request.urlopen(
                        urllib.request.Request(image_to_send, headers={"User-Agent": "Mozilla/5.0"})
                    ).read()
                    r = requests.post(
                        f"{self.API}/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
                        data={
                            "chat_id": TELEGRAM_CHAT_ID,
                            "caption": caption[:1024],
                            "parse_mode": "HTML"
                        },
                        files={"photo": ("image.jpg", img_data, "image/jpeg")}
                    )
                except Exception:
                    # Si échec image, envoyer texte seulement
                    r = requests.post(
                        f"{self.API}/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                        data={
                            "chat_id": TELEGRAM_CHAT_ID,
                            "text": caption[:4096],
                            "parse_mode": "HTML"
                        }
                    )
            r.raise_for_status()
            log.info(f"✅ Telegram envoyé : {product.title[:40]}")
            return True
        except Exception as e:
            log.error(f"Erreur Telegram : {e}")
            return False

    def send_summary(self, products) -> bool:
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            return False
        try:
            text = (
                f"🚀 <b>ShopForYou — Rapport du {datetime.now().strftime('%d/%m/%Y')}</b>\n\n"
                f"✅ {len(products)} produits traités\n"
                f"🌐 shopforyou31.fr\n\n"
            )
            for i, p in enumerate(products, 1):
                text += f"{i}. {p.emoji} {p.title[:50]} — {p.price:.2f}€\n"
            requests.post(
                f"{self.API}/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
            )
            return True
        except Exception as e:
            log.error(f"Erreur résumé Telegram : {e}")
            return False

# ── MODULE 4 : GÉNÉRATION VIDÉO TIKTOK ────────────────────────────────────────
class TikTokVideoGenerator:
    """Génère une vidéo MP4 avec moviepy."""

    def generate(self, product: Product, hook: str) -> Optional[str]:
        try:
            import urllib.request
            from moviepy.editor import (
                ColorClip, ImageClip, TextClip, CompositeVideoClip
            )
            tmp_img = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            if product.image_url:
                urllib.request.urlretrieve(product.image_url, tmp_img.name)
            duration = 15
            bg = ColorClip(size=(1080, 1920), color=(15, 15, 15), duration=duration)
            clips = [bg]
            try:
                img = ImageClip(tmp_img.name).resize(height=900).set_position("center").set_duration(duration)
                clips.append(img)
            except Exception:
                pass
            texts = [
                (hook[:40], 80, "white", 1150),
                (f"⭐ {product.rating}/5 · {product.reviews} avis", 50, "#FFD700", 1300),
                (f"{product.price:.2f}€ seulement", 60, "#FF9900", 1400),
                ("👉 shopforyou31.fr", 55, "#E8784A", 1550),
            ]
            for text, size, color, y in texts:
                try:
                    tc = TextClip(text, fontsize=size, color=color,
                                  font="DejaVu-Sans-Bold", method="caption",
                                  size=(1000, None)).set_position(("center", y)).set_duration(duration)
                    clips.append(tc)
                except Exception:
                    pass
            out = tempfile.mktemp(suffix=".mp4")
            CompositeVideoClip(clips).write_videofile(out, fps=30, codec="libx264", audio=False, logger=None)
            log.info(f"✅ Vidéo TikTok générée : {out}")
            return out
        except Exception as e:
            log.error(f"Erreur génération vidéo : {e}")
            return None

# ── ORCHESTRATEUR ───────────────────────────────────────────────────────────────
class ShopForYouAgent:

    def __init__(self):
        self.scanner  = AmazonScanner()
        self.updater  = ShopUpdater()
        self.telegram = TelegramNotifier()
        self.tiktok   = TikTokVideoGenerator()
        self.image_gen = ImageGenerator()

    def run(self):
        log.info("=" * 60)
        log.info(f"🚀 Cycle ShopForYou — {datetime.now().strftime('%d/%m/%Y %H:%M')}")

        products = self.scanner.scan()
        if not products:
            log.warning("Aucun produit trouvé — utilisation produit par défaut")
            products = [Product(
                title="STC Chaussettes Paillettes Pipelette Bleu",
                price=5.70, rating=4.8, reviews=145,
                asin="B0DS6K72MD",
                affiliate_url="https://www.amazon.fr/dp/B0DS6K72MD?tag=shopforyou099-21",
                image_url="https://m.media-amazon.com/images/I/71YnNpHKHNL._AC_SX466_.jpg", category="mode", emoji="🧦", score=95.0
            )]

        log.info(f"Top produit : {products[0].title[:50]} ({products[0].price}€)")
        # Ne mettre à jour la boutique que si de vrais produits sont trouvés
        if products[0].asin != "B0DS6K72MD":
            self.updater.update(products)
        else:
            log.info("Produit par défaut — boutique non modifiée")

        for i, product in enumerate(products):
            hook = random.choice(HOOKS).replace("{price}", str(int(product.price)))
            log.info(f"Produit {i+1}/{len(products)} : {product.title[:40]}")
            # Toujours générer une image IA
            ai_image = self.image_gen.generate(product.title, product.category)
            self.telegram.send_product(product, hook, ai_image)
            time.sleep(random.uniform(5, 10))
            self.tiktok.generate(product, hook)
            time.sleep(random.uniform(5, 10))

        self.telegram.send_summary(products)
        log.info("✅ Cycle terminé !")

    def start(self):
        log.info(f"🟢 Agent démarré — Publication à {PUBLISH_HOUR} chaque jour")
        schedule.every().day.at(PUBLISH_HOUR).do(self.run)
        self.run()
        while True:
            schedule.run_pending()
            time.sleep(60)

if __name__ == "__main__":
    ShopForYouAgent().start()
