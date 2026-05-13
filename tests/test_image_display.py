import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "index.html").read_text(encoding="utf-8")

import sys
sys.path.insert(0, str(ROOT))
import _sync_feishu_to_web as sync


class ProductImageDisplayTests(unittest.TestCase):
    def test_candidate_cards_use_prominent_product_media_with_placeholder_label(self):
        self.assertIn("product-media-thumb", HTML)
        self.assertIn("待补图", HTML)
        self.assertIn("alt=", HTML)
        self.assertIn('decoding="async"', HTML)

    def test_detail_top_has_product_image_hero_container(self):
        self.assertIn('id="heroImage"', HTML)
        self.assertIn("detail-hero-card", HTML)
        self.assertIn("renderHeroImage", HTML)
        self.assertIn("product-image-large", HTML)

    def test_discovery_top10_and_top4_render_images_or_placeholders(self):
        self.assertIn("discoveryProductImage", HTML)
        self.assertIn("top10Rows=top10.map", HTML)
        self.assertRegex(HTML, r"top10Rows=top10\.map\(r=>.*discoveryProductImage\(r")
        self.assertRegex(HTML, r"top4Html=top4\.map\(r=>.*discoveryProductImage\(r")

    def test_mobile_styles_keep_images_from_squeezing_copy(self):
        self.assertIn("@media(max-width:640px)", HTML)
        self.assertIn(".item{grid-template-columns:76px 1fr", HTML)
        self.assertIn(".detail-hero-card{grid-template-columns:1fr", HTML)
        self.assertIn(".product-media-thumb{width:76px", HTML)
        self.assertIn("mobile-safe-text", HTML)
        self.assertIn("stamp-line", HTML)
        self.assertIn(".snapshot-grid,.evidence-matrix,.decision-grid,.owner-flow{grid-template-columns:1fr}", HTML)

    def test_dedup_overlay_marks_and_folds_duplicate_candidates(self):
        self.assertIn("const DEDUP_RULES", HTML)
        self.assertIn("已存在", HTML)
        self.assertIn("变体", HTML)
        self.assertIn("isFoldedCandidate", HTML)
        self.assertIn("dedupRelatedBlock", HTML)
        self.assertIn("相关子方向 / 历史推荐", HTML)

    def test_discovery_top10_has_dedup_status_column(self):
        self.assertIn("Top10 候选池（新增 / 已存在 / 变体状态）", HTML)
        self.assertIn("去重状态", HTML)
        self.assertIn("dedupPill(rule.status,rule.type)", HTML)

    def test_sync_accepts_known_public_image_headers(self):
        row = {
            "产品方向": "测试产品",
            "主图URL": "查看 https://static.example.com/p/test-image.jpg",
        }
        item = {"product": "测试产品"}
        sync.apply_image_url(item, row)
        self.assertEqual(item["imageUrl"], "https://static.example.com/p/test-image.jpg")

    def test_sync_rejects_signed_or_tokenized_image_urls(self):
        self.assertEqual(sync.clean_public_image_url("https://example.com/a.jpg?token=secret"), "")
        self.assertEqual(sync.clean_public_image_url("https://example.com/a.jpg?X-Amz-Signature=abc"), "")
        self.assertEqual(sync.image_url_from_row({"图片URL": "https://example.com/a.jpg?Expires=123"}), "")


if __name__ == "__main__":
    unittest.main()
