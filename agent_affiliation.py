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
            api_key = os.getenv("SCRAPER_API_KEY", "")
            if not api_key:
                log.warning("SCRAPER_API_KEY manquant")
                return None
            # Utiliser l'endpoint Amazon structuré de ScraperAPI
            import urllib.parse
            query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get('k', [''])[0]
            scraper_url = f"https://api.scraperapi.com/structured/amazon/search"
            r = requests.get(scraper_url, params={
                "api_key": api_key,
                "query": query,
                "country": "fr",
                "tld": "fr"
            }, timeout=60)
            r.raise_for_status()
            log.info(f"ScraperAPI structured OK — {len(r.text)} chars")
            return r.text
        except Exception as e:
            log.warning(f"Fetch error {url}: {e}")
            return None

    def parse(self, html: str, niche: dict) -> List[Product]:
        try:
            data = json.loads(html)
            products = []
            for item in data.get("results", []):
                try:
                    title = item.get("name", "")
                    if not title:
                        continue
                    asin = item.get("asin", "")
                    if not asin:
                        continue
                    price_str = str(item.get("price", "0")).replace(",", ".").replace("€", "").strip()
                    price = float("".join(c for c in price_str if c.isdigit() or c == ".") or 0)
                    if not (MIN_PRICE <= price <= MAX_PRICE):
                        continue
                    rating = float(str(item.get("stars", "0")).replace(",", ".") or 0)
                    if rating < MIN_RATING:
                        continue
                    image_url = item.get("image", "")
                    affiliate_url = f"https://www.amazon.fr/dp/{asin}?tag={AMAZON_TAG}"
                    import math
                    score = (rating * 20) + max(0, (1 - price / MAX_PRICE) * 10)
                    products.append(Product(
                        title=title, price=price, rating=rating, reviews=0,
                        asin=asin, affiliate_url=affiliate_url, image_url=image_url,
                        category=niche["category"], emoji=niche["emoji"], score=round(score, 2)
                    ))
                except Exception:
                    continue
            log.info(f"Produits parsés : {len(products)}")
            return products
        except Exception as e:
            log.error(f"Erreur parsing JSON : {e}")
            return []

    def scan(self) -> List[Product]:
        all_products = []

        # Une niche par catégorie
        categories = {
            "mode":     [n for n in NICHES if n["category"] == "mode"],
            "maison":   [n for n in NICHES if n["category"] == "maison"],
            "bienetre": [n for n in NICHES if n["category"] == "bienetre"],
            "beaute":   [n for n in NICHES if n["category"] == "beaute"],
            "cuisine":  [n for n in NICHES if n["category"] == "cuisine"],
        }

        best_per_category = {}

        for cat, niches in categories.items():
            cat_products = []
            for niche in niches:
                url = f"{self.BASE}?k={requests.utils.quote(niche['query'])}&s=review-rank"
                log.info(f"Scan [{cat}]: {niche['query']}")
                html = self.fetch(url)
                if html:
                    products = self.parse(html, niche)
                    cat_products.extend(products)
                time.sleep(random.uniform(2, 4))

            if cat_products:
                cat_products.sort(key=lambda x: x.score, reverse=True)
                best = cat_products[0]
                best_per_category[cat] = best
                log.info(f"✅ [{cat}] Meilleur : {best.title[:40]} ({best.price}€, {best.reviews} avis)")
            else:
                log.warning(f"❌ [{cat}] Aucun produit trouvé")

        result = list(best_per_category.values())
        log.info(f"Total produits sélectionnés : {len(result)}/5")
        return result

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
                    "version": "black-forest-labs/flux-schnell",
                    "input": {
                        "prompt": prompt,
                        "aspect_ratio": "9:16",
                        "num_outputs": 1,
                        "output_format": "jpg"
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


# ── MODULE 2 : MISE À JOUR BOUTIQUE ─────────────────────────────────────────────
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

    def build_card(self, p) -> str:
        stars = "★" * int(p.rating) + "☆" * (5 - int(p.rating))
        cat_label = CAT_LABELS.get(p.category, p.category.capitalize())
        title_short = p.title[:60] + "..." if len(p.title) > 60 else p.title
        return f'''    <div class="card" data-cat="{p.category}">
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

    def update(self, products) -> bool:
        if not GITHUB_TOKEN:
            log.warning("GITHUB_TOKEN manquant — boutique non mise à jour")
            return False
        try:
            content, sha = self.get_file()
            new_cards = "\n".join(self.build_card(p) for p in products)
            marker_start = "<!-- PRODUITS_AUTO_START -->"
            marker_end = "<!-- PRODUITS_AUTO_END -->"
            if marker_start in content:
                import re
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


# ── MODULE 4 : NOTIFICATION TELEGRAM ─────────────────────────────────────────
class TelegramNotifier:
    """Envoie les posts sur Telegram pour publication manuelle."""

    API = "https://api.telegram.org"

    def send_product(self, product, hook: str) -> bool:
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
            self.telegram.send_product(product, hook)
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
