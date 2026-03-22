"""
fields.py — Predefined extraction catalog for Scout.

Every run attempts to find selectors for all 35 fields below.
The LLM's job is *search*, not *invention* — it either finds a selector
for each field or marks it as not found.

Categories: seo | content | ecommerce | structure
"""

from __future__ import annotations

FIELD_CATALOG: list[dict] = [
    # ------------------------------------------------------------------
    # SEO (12)
    # ------------------------------------------------------------------
    {
        "field_name": "page_title",
        "description": "<title> tag text content",
        "category": "seo",
    },
    {
        "field_name": "meta_description",
        "description": "<meta name=\"description\"> content attribute",
        "category": "seo",
    },
    {
        "field_name": "meta_keywords",
        "description": "<meta name=\"keywords\"> content attribute",
        "category": "seo",
    },
    {
        "field_name": "canonical_url",
        "description": "<link rel=\"canonical\"> href attribute",
        "category": "seo",
    },
    {
        "field_name": "og_title",
        "description": "<meta property=\"og:title\"> content attribute",
        "category": "seo",
    },
    {
        "field_name": "og_description",
        "description": "<meta property=\"og:description\"> content attribute",
        "category": "seo",
    },
    {
        "field_name": "og_image",
        "description": "<meta property=\"og:image\"> content attribute (image URL)",
        "category": "seo",
    },
    {
        "field_name": "og_type",
        "description": "<meta property=\"og:type\"> content attribute (e.g. article, product)",
        "category": "seo",
    },
    {
        "field_name": "meta_robots",
        "description": "<meta name=\"robots\"> content attribute (e.g. index,follow)",
        "category": "seo",
    },
    {
        "field_name": "structured_data",
        "description": "<script type=\"application/ld+json\"> JSON-LD structured data blocks",
        "category": "seo",
    },
    {
        "field_name": "hreflang",
        "description": "<link rel=\"alternate\" hreflang=\"...\"> international targeting tags",
        "category": "seo",
    },
    {
        "field_name": "page_lang",
        "description": "<html lang=\"...\"> page language attribute",
        "category": "seo",
    },

    # ------------------------------------------------------------------
    # Content (10)
    # ------------------------------------------------------------------
    {
        "field_name": "h1",
        "description": "Primary H1 heading — the main page or article title",
        "category": "content",
    },
    {
        "field_name": "h2_list",
        "description": "All H2 subheadings (multiple elements expected)",
        "category": "content",
    },
    {
        "field_name": "article_body",
        "description": "Main article or body content container (the prose, not boilerplate)",
        "category": "content",
    },
    {
        "field_name": "author",
        "description": "Author name — byline, author bio link, or name in metadata",
        "category": "content",
    },
    {
        "field_name": "publish_date",
        "description": "Publication or posted date — often in <time> or a date-stamped element",
        "category": "content",
    },
    {
        "field_name": "modified_date",
        "description": "Last modified or updated date",
        "category": "content",
    },
    {
        "field_name": "featured_image",
        "description": "Hero or featured image — the primary <img> associated with the article/page",
        "category": "content",
    },
    {
        "field_name": "article_category",
        "description": "Article category, section, or topic label (e.g. 'Technology', 'Sports')",
        "category": "content",
    },
    {
        "field_name": "article_tags",
        "description": "Tags, labels, or topic keywords associated with the article",
        "category": "content",
    },
    {
        "field_name": "breadcrumbs",
        "description": "Breadcrumb navigation trail showing page hierarchy",
        "category": "content",
    },

    # ------------------------------------------------------------------
    # E-commerce (8)
    # ------------------------------------------------------------------
    {
        "field_name": "product_name",
        "description": "Product title or name — the main heading on a product page",
        "category": "ecommerce",
    },
    {
        "field_name": "product_price",
        "description": "Current or sale price of the product",
        "category": "ecommerce",
    },
    {
        "field_name": "product_original_price",
        "description": "Original price before discount (crossed-out / was-price)",
        "category": "ecommerce",
    },
    {
        "field_name": "product_description",
        "description": "Product description or details text",
        "category": "ecommerce",
    },
    {
        "field_name": "product_sku",
        "description": "Product SKU, model number, or product ID",
        "category": "ecommerce",
    },
    {
        "field_name": "product_availability",
        "description": "Stock status — in stock / out of stock / ships in X days",
        "category": "ecommerce",
    },
    {
        "field_name": "product_rating",
        "description": "Numeric star rating value (e.g. 4.5)",
        "category": "ecommerce",
    },
    {
        "field_name": "product_review_count",
        "description": "Total number of customer reviews or ratings",
        "category": "ecommerce",
    },

    # ------------------------------------------------------------------
    # Structure (5)
    # ------------------------------------------------------------------
    {
        "field_name": "primary_nav",
        "description": "Main / primary navigation menu links",
        "category": "structure",
    },
    {
        "field_name": "site_logo",
        "description": "Site logo image element",
        "category": "structure",
    },
    {
        "field_name": "search_form",
        "description": "Site search input or search form element",
        "category": "structure",
    },
    {
        "field_name": "pagination",
        "description": "Pagination controls — next/previous page links or page number list",
        "category": "structure",
    },
    {
        "field_name": "footer_links",
        "description": "Footer navigation links or footer sitemap",
        "category": "structure",
    },
]

# Convenience: field names grouped by category
CATEGORIES: dict[str, list[str]] = {}
for _f in FIELD_CATALOG:
    CATEGORIES.setdefault(_f["category"], []).append(_f["field_name"])
