#!/usr/bin/env python3
"""
Agent Affiliation Amazon -> TikTok
4 modules : AmazonScanner, ContentGenerator, TikTokPublisher, EmailReporter
"""

import os
import time
import random
import smtplib
import logging
import requests
import schedule
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dataclasses import dataclass
from typing import List, Optional

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── CONFIGURATION ──────────────────────────────────────────────────────────────
AMAZON_TAG        = os.getenv("AMAZON_TAG", "shopforyou099-21")
EMAIL_FROM        = os.getenv("EMAIL_FROM", "")
EMAIL_TO          = os.getenv("EMAIL_TO", "")
EMAIL_PASSWORD    = os.getenv("EMAIL_PASSWORD", "")
TIKTOK_SESSION_ID = os.getenv("TIKTOK_SESSION_ID", "")
MIN_RATING        = float(os.getenv("MIN_RATING", "4.0"))
MAX_PRICE         = float(os.getenv("MAX_PRICE", "50.0"))
MIN_REVIEWS       = int(os.getenv("MIN_REVIEWS", "100"))

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Accept-Language": "fr-FR,fr;q=0.9",
}

CATEGORIES = [
    "https://www.amazon.fr/s?k=gadget+cuisine&tag={tag}",
    "https://www.amazon.fr/s?k=accessoire+sport&tag={tag}",
    "https://www.amazon.fr/s?k=organisation+maison&tag={tag}",
    "https://www.amazon.fr/s?k=soin+visage&tag={tag}",
    "https://www.amazon.fr/s?k=gadget+bureau&tag={tag}",
]


# ── DATA CLASSES ───────────────────────────────────────────────────────────────
@dataclass
class Product:
    title: str
    url: str
    price: float
    rating: float
    reviews: int
    asin: str
    image_url: str = ""
    score: float = 0.0
    affiliate_url: str = ""


@dataclass
class VideoRecord:
    product_title: str
    tiktok_url: str
    published_at: str
    score: float
    price: float
    rating: float


# ── MODULE 1 : AMAZON SCANNER ──────────────────────────────────────────────────
class AmazonScanner:
    """Scanne Amazon, filtre par note/prix/avis, calcule un score de pertinence."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _fetch(self, url: str):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
                page = browser.new_context().new_page()
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                time.sleep(random.uniform(2, 4))
                html = page.content()
                browser.close()
            return BeautifulSoup(html, "html.parser")
        except Exception as e:
            logger.warning(f"Erreur fetch {url}: {e}")
            return None

    def _parse_results(self, soup, tag: str) -> List[Product]:
        products = []
        for item in soup.select('[data-component-type="s-search-result"]'):
            try:
                title_el = item.select_one("h2 a span")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                link_el = item.select_one("h2 a")
                path = link_el["href"] if link_el else ""
                asin = path.split("/dp/")[1].split("/")[0] if "/dp/" in path else ""
                if not asin:
                    continue
                url = f"https://www.amazon.fr/dp/{asin}?tag={tag}"
                price_el = item.select_one(".a-price .a-offscreen")
                price_txt = price_el.get_text(strip=True).replace(" ","").replace(",",".").replace("EUR","") if price_el else "0"
                price = float("".join(c for c in price_txt if c.isdigit() or c == ".") or 0)
                rating_el = item.select_one(".a-icon-alt")
                rating_txt = rating_el.get_text(strip=True).split(" ")[0].replace(",",".") if rating_el else "0"
                rating = float(rating_txt or 0)
                reviews_el = item.select_one('[data-component-type="s-client-side-analytics"] .a-size-base')
                reviews_txt = reviews_el.get_text(strip=True).replace(" ","").replace(",","") if reviews_el else "0"
                reviews = int("".join(c for c in reviews_txt if c.isdigit()) or 0)
                img_el = item.select_one("img.s-image")
                image_url = img_el["src"] if img_el else ""
                products.append(Product(
                    title=title, url=url, price=price, rating=rating,
                    reviews=reviews, asin=asin, image_url=image_url, affiliate_url=url
                ))
            except Exception as e:
                logger.debug(f"Parse error: {e}")
        return products

    @staticmethod
    def _compute_score(p: Product) -> float:
        import math
        r_score = p.rating * 20
        v_score = math.log10(p.reviews + 1) * 15
        p_score = max(0, (1 - p.price / MAX_PRICE) * 10) if MAX_PRICE else 0
        return round(min(r_score + v_score + p_score, 100), 2)

    def scan(self) -> List[Product]:
        all_products: List[Product] = []
        for url_tpl in CATEGORIES:
            url = url_tpl.format(tag=AMAZON_TAG)
            logger.info(f"Scan: {url}")
            soup = self._fetch(url)
            if soup:
                all_products.extend(self._parse_results(soup, AMAZON_TAG))
            time.sleep(random.uniform(2, 5))
        filtered = [
            p for p in all_products
            if p.rating >= MIN_RATING and p.price <= MAX_PRICE and p.reviews >= MIN_REVIEWS
        ]
        for p in filtered:
            p.score = self._compute_score(p)
        filtered.sort(key=lambda x: x.score, reverse=True)
        logger.info(f"Produits retenus : {len(filtered)}/{len(all_products)}")
        return filtered[:10]


# ── MODULE 2 : CONTENT GENERATOR ──────────────────────────────────────────────
class ContentGenerator:
    """Genere hook, script sequence, description et hashtags."""

    HOOKS = [
        "Tu DOIS voir ce produit Amazon !",
        "J'ai trouve LA pepite Amazon du moment",
        "Ce produit a change ma vie quotidienne",
        "Amazon cache ce produit incroyable",
        "Le meilleur achat Amazon a moins de {price}EUR",
    ]
    OUTROS = [
        "Lien en bio | Code promo dispo !",
        "Lien direct en bio - livraison rapide !",
        "Clique sur le lien en bio avant rupture de stock !",
    ]
    HASHTAGS = [
        "#amazon", "#amazonfrance", "#astucemaison", "#bonplan",
        "#produitamazon", "#tiktokshop", "#trouvailleamazon",
        "#lifehack", "#gadget", "#viral", "#fyp", "#pourtoi",
        "#bonneaffaire", "#shoppingamazon", "#must_have",
    ]

    def generate(self, product: Product) -> dict:
        hook = random.choice(self.HOOKS).format(price=int(product.price))
        script_lines = [
            f"Hook : {hook}", "",
            f"Produit : {product.title[:80]}", "",
            f"Note : {product.rating}/5 - {product.reviews} avis verifies",
            f"Prix : {product.price:.2f} EUR", "",
            "Pourquoi c'est top :",
            "  - Qualite exceptionnelle pour le prix",
            "  - Livraison rapide Amazon Prime",
            "  - Retours gratuits 30 jours", "",
            f"Lien : {product.affiliate_url}", "",
            random.choice(self.OUTROS),
        ]
        description = (
            f"{hook}\n\n{product.title[:100]}\n"
            f"{product.rating}/5 | {product.reviews} avis | {product.price:.2f} EUR"
            f"\n\nLien en bio !"
        )
        hashtags = " ".join(random.sample(self.HASHTAGS, min(10, len(self.HASHTAGS))))
        return {
            "hook": hook,
            "script": "\n".join(script_lines),
            "description": description,
            "hashtags": hashtags,
            "full_caption": f"{description}\n\n{hashtags}",
        }


# ── MODULE 3 : TIKTOK PUBLISHER ───────────────────────────────────────────────
class TikTokPublisher:
    """Publie une video TikTok via Playwright (navigateur headless)."""

    UPLOAD_URL = "https://www.tiktok.com/upload"

    def __init__(self, session_id: str):
        self.session_id = session_id

    def _make_video(self, product: Product, content: dict) -> str:
        import textwrap
        import tempfile
        import urllib.request
        from moviepy.editor import ImageClip, TextClip, CompositeVideoClip, ColorClip

        tmp_img = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        try:
            if product.image_url:
                urllib.request.urlretrieve(product.image_url, tmp_img.name)
        except Exception:
            pass

        duration = 15
        clips = [ColorClip(size=(1080, 1920), color=(15, 15, 15), duration=duration)]
        try:
            clips.append(
                ImageClip(tmp_img.name).resize(height=800)
                .set_position(("center", 200)).set_duration(duration)
            )
        except Exception:
            pass
        try:
            hook_text = textwrap.fill(content["hook"], width=30)
            clips.append(
                TextClip(hook_text, fontsize=60, color="white",
                         font="DejaVu-Sans-Bold", method="caption", size=(1000, None))
                .set_position(("center", 1100)).set_duration(duration)
            )
        except Exception:
            pass
        try:
            clips.append(
                TextClip(f"{product.price:.2f}EUR  {product.rating}/5",
                         fontsize=50, color="#FFD700", font="DejaVu-Sans-Bold")
                .set_position(("center", 1250)).set_duration(duration)
            )
        except Exception:
            pass

        out_path = tempfile.mktemp(suffix=".mp4")
        CompositeVideoClip(clips).write_videofile(
            out_path, fps=30, codec="libx264", audio=False, logger=None
        )
        return out_path

    def publish(self, product: Product, content: dict) -> Optional[str]:
        try:
            video_path = self._make_video(product, content)
            logger.info(f"Video generee : {video_path}")
        except Exception as e:
            logger.error(f"Generation video echouee : {e}")
            return None

        published_url = None
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            context = browser.new_context(
                user_agent=HEADERS["User-Agent"],
                viewport={"width": 1280, "height": 800}
            )
            context.add_cookies([{
                "name": "sessionid", "value": self.session_id,
                "domain": ".tiktok.com", "path": "/",
                "secure": True, "httpOnly": True, "sameSite": "None"
            }])
            page = context.new_page()
            try:
                page.goto(self.UPLOAD_URL, timeout=60000)
                page.wait_for_load_state("networkidle", timeout=30000)
                file_input = page.query_selector('input[type="file"]')
                if not file_input:
                    logger.error("Champ file introuvable")
                    return None
                file_input.set_input_files(video_path)
                page.wait_for_timeout(8000)
                caption_sel = 'div[contenteditable="true"]'
                page.wait_for_selector(caption_sel, timeout=30000)
                caption_box = page.query_selector(caption_sel)
                if caption_box:
                    caption_box.click()
                    caption_box.fill(content["full_caption"][:2200])
                page.wait_for_timeout(2000)
                publish_btn = (
                    page.query_selector('button[data-e2e="upload-btn-post"]') or
                    page.query_selector('button:has-text("Publier")')
                )
                if publish_btn:
                    publish_btn.click()
                    page.wait_for_timeout(5000)
                    published_url = page.url
                    logger.info(f"Publie : {published_url}")
                else:
                    logger.error("Bouton Publier introuvable")
            except Exception as e:
                logger.error(f"Erreur publication TikTok : {e}")
            finally:
                context.close()
                browser.close()
        return published_url


# ── MODULE 4 : EMAIL REPORTER ──────────────────────────────────────────────────
class EmailReporter:
    """Envoie un rapport HTML quotidien avec tableau des videos publiees."""

    SMTP_HOST = "smtp.gmail.com"
    SMTP_PORT = 587

    def _build_html(self, records: List[VideoRecord]) -> str:
        rows = "".join(
            f"<tr>"
            f"<td style='padding:8px;border:1px solid #ddd'>{r.published_at}</td>"
            f"<td style='padding:8px;border:1px solid #ddd'>{r.product_title[:60]}</td>"
            f"<td style='padding:8px;border:1px solid #ddd'>{r.price:.2f} EUR</td>"
            f"<td style='padding:8px;border:1px solid #ddd'>{r.rating}/5</td>"
            f"<td style='padding:8px;border:1px solid #ddd'>{r.score}</td>"
            f"<td style='padding:8px;border:1px solid #ddd'><a href='{r.tiktok_url}'>Voir</a></td>"
            f"</tr>"
            for r in records
        )
        avg = sum(r.score for r in records) / len(records) if records else 0
        date_str = datetime.now().strftime("%d/%m/%Y a %H:%M")
        return (
            '<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8">'
            '<title>Rapport Affiliation</title>'
            '<style>'
            'body{font-family:Arial,sans-serif;background:#f5f5f5;color:#333}'
            '.container{max-width:900px;margin:30px auto;background:#fff;padding:30px;'
            'border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.1)}'
            'h1{color:#FF0050}'
            'table{width:100%;border-collapse:collapse;margin-top:20px}'
            'th{background:#FF0050;color:#fff;padding:10px;text-align:left}'
            'tr:nth-child(even){background:#fafafa}'
            '.stat{display:inline-block;background:#FF0050;color:#fff;'
            'padding:10px 20px;border-radius:5px;margin:5px;font-size:18px}'
            '</style></head><body><div class="container">'
            '<h1>Rapport Affiliation Amazon - TikTok</h1>'
            f'<p>Genere le {date_str}</p>'
            f'<div><span class="stat">{len(records)} video(s)</span>'
            f'<span class="stat">Score moyen : {avg:.1f}</span></div>'
            '<table><thead><tr><th>Date</th><th>Produit</th><th>Prix</th>'
            '<th>Note</th><th>Score</th><th>TikTok</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div></body></html>'
        )

    def send(self, records: List[VideoRecord]) -> bool:
        if not all([EMAIL_FROM, EMAIL_TO, EMAIL_PASSWORD]):
            logger.warning("Email non configure - rapport ignore")
            return False
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[Affiliation] Rapport du {datetime.now().strftime('%d/%m/%Y')}"
            msg["From"] = EMAIL_FROM
            msg["To"] = EMAIL_TO
            msg.attach(MIMEText(self._build_html(records), "html"))
            with smtplib.SMTP(self.SMTP_HOST, self.SMTP_PORT) as server:
                server.ehlo()
                server.starttls()
                server.login(EMAIL_FROM, EMAIL_PASSWORD)
                server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
            logger.info(f"Rapport envoye a {EMAIL_TO}")
            return True
        except Exception as e:
            logger.error(f"Erreur envoi email : {e}")
            return False


# ── ORCHESTRATEUR PRINCIPAL ────────────────────────────────────────────────────
def main():
    logger.info("=== Agent Affiliation demarre ===")

    # Produits hardcodés (fiables, déjà validés)
    products = [
        Product(
            title="STC Chaussettes paillettes pipelette bleu",
            url="https://amzn.to/4ddmLLI",
            price=5.70,
            rating=4.8,
            reviews=145,
            asin="B0DS6K72MD",
            image_url="",
            affiliate_url="https://amzn.to/4ddmLLI",
            score=95.0
        )
    ]

    generator = ContentGenerator()
    publisher = TikTokPublisher(session_id=TIKTOK_SESSION_ID)
    reporter  = EmailReporter()
    records   = []

    for product in products[:3]:
        content = generator.generate(product)
        logger.info(f"Hook genere : {content['hook']}")
        if TIKTOK_SESSION_ID:
            tiktok_url = publisher.publish(product, content)
        else:
            tiktok_url = "simulation"
            logger.warning("TIKTOK_SESSION_ID manquant")
        records.append(VideoRecord(
            product_title=product.title,
            tiktok_url=tiktok_url or "erreur",
            published_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
            score=product.score,
            price=product.price,
            rating=product.rating,
        ))

    reporter.send(records)
    logger.info("=== Agent termine ===")

if __name__ == "__main__":
    import schedule

    def job():
        logger.info("=== Lancement cycle automatique ===")
        main()

    # Publication chaque jour à 10h00 (heure Railway = UTC, donc 10h France = 8h UTC)
    schedule.every().day.at("08:00").do(job)

    logger.info("✅ Scheduler démarré — publication chaque jour à 10h00 (France)")
    logger.info("⏳ Prochain cycle dans : " + str(schedule.next_run()))

    # Lancement immédiat au démarrage
    job()

    # Boucle infinie
    while True:
        schedule.run_pending()
        time.sleep(30)
