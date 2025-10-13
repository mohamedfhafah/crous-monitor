#!/usr/bin/env python3
"""
Enhanced CROUS Scraper
Specialized scraper for CROUS housing websites with improved parsing capabilities.
"""

import re
import time
import logging
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class EnhancedCROUSScraper:
    def __init__(self, session: requests.Session = None):
        """Initialize the enhanced scraper."""
        self.session = session or requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })

    def scrape_main_search_page(self, url: str) -> List[Dict]:
        """Scrape the main CROUS search page with enhanced parsing."""
        try:
            logger.info(f"Scraping main search page: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')
            listings = []

            # Check for "no results" message
            no_results_patterns = [
                "Aucun logement trouvé",
                "0 logements trouvés",
                "page 0 sur 0"
            ]

            page_text = soup.get_text()
            if any(pattern in page_text for pattern in no_results_patterns):
                logger.info("No housing listings found on this page")
                return listings

            # Method 1: Look for structured listing cards
            listing_cards = self.find_listing_cards(soup)
            if listing_cards:
                logger.info(f"Found {len(listing_cards)} listing cards")
            for card in listing_cards:
                listing = self.parse_listing_card(card, url)
                if listing:
                    listings.append(listing)

            # Method 2: Look for list-based listings
            if not listings:
                list_items = self.find_list_items(soup)
                if list_items:
                    logger.info(f"Found {len(list_items)} list items")
                    for item in list_items:
                        listing = self.parse_list_item(item, url)
                        if listing:
                            listings.append(listing)

            # Method 3: Parse markdown-style content
            if not listings:
                markdown_listings = self.parse_markdown_content(soup, url)
                listings.extend(markdown_listings)

            logger.info(f"Total Marseille listings found: {len(listings)}")
            return listings

        except requests.RequestException as e:
            logger.error(f"Network error scraping {url}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error scraping {url}: {e}")
            return []

    def find_listing_cards(self, soup: BeautifulSoup) -> List:
        """Find listing cards using various selectors."""
        selectors = [
            'div[class*="logement"]',
            'div[class*="residence"]',
            'div[class*="listing"]',
            'div[class*="card"]',
            'li[class*="logement"]',
            'li[class*="residence"]',
            'article',
            '.result-item',
            '.housing-item'
        ]

        all_cards = []
        for selector in selectors:
            cards = soup.select(selector)
            if cards:
                all_cards.extend(cards)
                break

        return all_cards

    def find_list_items(self, soup: BeautifulSoup) -> List:
        """Find list-based housing listings."""
        selectors = [
            'ul li',
            '.listings li',
            '.results li',
            'tbody tr'
        ]

        for selector in selectors:
            items = soup.select(selector)
            if items and len(items) > 0:
                return items

        return []

    def parse_listing_card(self, card, base_url: str) -> Optional[Dict]:
        """Parse a listing card element."""
        try:
            # Extract basic information
            residence_name = self.extract_text(card, [
                'h3', 'h4', '.title', '.residence-name', '.name'
            ])

            address = self.extract_text(card, [
                '.address', '.location', '.place', 'p'
            ])

            price = self.extract_price(card, [
                '.price', '.cost', '.rent', '.prix'
            ])

            # Generate listing hash for deduplication
            listing_hash = self.generate_listing_hash(residence_name, address, price)

            listing = {
                'residence_name': residence_name,
                'address': address,
                'price': price,
                'url': base_url,
                'listing_hash': listing_hash
            }

            # Add optional fields
            listing.update(self.extract_additional_info(card))

            return listing

        except Exception as e:
            logger.error(f"Error parsing listing card: {e}")
            return None

    def parse_list_item(self, item, base_url: str) -> Optional[Dict]:
        """Parse a list item element."""
        try:
            # Extract information from table cells or list items
            cells = item.find_all(['td', 'div', 'span'])
            if len(cells) < 3:
                return None

            residence_name = cells[0].get_text(strip=True) if cells[0] else "Unknown"
            address = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            price_text = cells[2].get_text(strip=True) if len(cells) > 2 else ""

            price = self.extract_price_from_text(price_text)

            listing_hash = self.generate_listing_hash(residence_name, address, price)

            return {
                'residence_name': residence_name,
                'address': address,
                'price': price,
                'url': base_url,
                'listing_hash': listing_hash
            }

        except Exception as e:
            logger.error(f"Error parsing list item: {e}")
            return None

    def parse_markdown_content(self, soup: BeautifulSoup, base_url: str) -> List[Dict]:
        """Parse markdown-style housing listings."""
        listings = []

        # Look for pre-formatted text or code blocks
        pre_blocks = soup.find_all(['pre', 'code'])
        for block in pre_blocks:
            text = block.get_text()
            if 'logement' in text.lower() or 'chambre' in text.lower():
                # Parse markdown-style listings
                parsed_listings = self.parse_markdown_listings(text, base_url)
                listings.extend(parsed_listings)

        return listings

    def parse_markdown_listings(self, text: str, base_url: str) -> List[Dict]:
        """Parse markdown-formatted housing listings."""
        listings = []
        lines = text.split('\n')

        for line in lines:
            line = line.strip()
            if not line or not ('€' in line or 'chambre' in line.lower()):
                continue

            try:
                # Extract information using regex
                price_match = re.search(r'(\d+(?:[,.]\d+)?)\s*€', line)
                price = float(price_match.group(1).replace(',', '.')) if price_match else None

                # Extract residence name
                name_match = re.search(r'(?:Résidence|Cite)\s*([^,\n]+)', line, re.IGNORECASE)
                residence_name = name_match.group(1).strip() if name_match else "Unknown Residence"

                listing_hash = self.generate_listing_hash(residence_name, "", price)

                listings.append({
                    'residence_name': residence_name,
                    'address': "Marseille",
                    'price': price,
                    'url': base_url,
                    'listing_hash': listing_hash
                })

            except Exception as e:
                logger.error(f"Error parsing markdown line: {e}")
                continue

        return listings

    def extract_text(self, element, selectors: List[str]) -> str:
        """Extract text from element using multiple selectors."""
        for selector in selectors:
            found = element.select_one(selector)
            if found:
                return found.get_text(strip=True)

        # Fallback: get direct text
        return element.get_text(strip=True)

    def extract_price(self, element, selectors: List[str]) -> Optional[float]:
        """Extract price from element."""
        for selector in selectors:
            found = element.select_one(selector)
            if found:
                text = found.get_text(strip=True)
                return self.extract_price_from_text(text)

        # Fallback: search in all text
        text = element.get_text()
        return self.extract_price_from_text(text)

    def extract_price_from_text(self, text: str) -> Optional[float]:
        """Extract numeric price from text."""
        if not text:
            return None

        # Find price patterns
        patterns = [
            r'(\d+(?:[,.]\d+)?)\s*€',
            r'€\s*(\d+(?:[,.]\d+)?)',
            r'(\d+(?:[,.]\d+)?)\s*euros?',
            r'prix\s*:\s*(\d+(?:[,.]\d+)?)'
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1).replace(',', '.'))
                except ValueError:
                    continue

        return None

    def extract_additional_info(self, element) -> Dict:
        """Extract additional information from listing card."""
        info = {}

        # Extract surface area
        surface_patterns = [
            r'(\d+(?:[,.]\d+)?)\s*m²',
            r'(\d+(?:[,.]\d+)?)\s*m2',
            r'surface\s*:\s*(\d+(?:[,.]\d+)?)'
        ]

        text = element.get_text()
        for pattern in surface_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                info['surface_area'] = f"{match.group(1)}m²"
                break

        # Extract housing type
        if 'studio' in text.lower():
            info['housing_type'] = 'Studio'
        elif 'chambre' in text.lower():
            info['housing_type'] = 'Chambre'
        elif 'colocation' in text.lower():
            info['housing_type'] = 'Colocation'
        elif 'individuel' in text.lower():
            info['housing_type'] = 'Individuel'

        return info

    def generate_listing_hash(self, residence_name: str, address: str, price: Optional[float]) -> str:
        """Generate a unique hash for listing deduplication."""
        import hashlib

        content = f"{residence_name}|{address}|{price}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def is_valid_listing(self, listing: Dict, filters: Dict) -> bool:
        """Check if listing meets filter criteria."""
        if not listing:
            return False

        # Price filter
        max_price = filters.get('max_price')
        if max_price and listing.get('price') and listing['price'] > max_price:
            return False

        # Housing type filter
        preferred_types = filters.get('preferred_types', [])
        if preferred_types:
            housing_type = listing.get('housing_type', '')
            if housing_type and housing_type not in preferred_types:
                return False

        return True
