#!/usr/bin/env python3
"""
CROUS Marseille Housing Monitor - Main Application
Enhanced version with improved scraping and notification capabilities.
"""

import asyncio
import json
import logging
import re
import sqlite3
import sys
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

import requests
from telegram import Bot
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Import our enhanced scraper
from enhanced_scraper import EnhancedCROUSScraper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('crous_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class CROUSMonitorMain:
    def __init__(self, config_file: str = 'config.json'):
        """Initialize the CROUS monitor with enhanced capabilities."""
        self.config = self.load_config(config_file)
        self.session = requests.Session()
        self.scraper = EnhancedCROUSScraper(self.session)
        self.db_path = 'crous_housing.db'
        self.init_database()

    def load_config(self, config_file: str) -> Dict:
        """Load configuration from JSON file with environment variable overrides."""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.info(f"Configuration loaded from {config_file}")
        except FileNotFoundError:
            logger.error(f"Configuration file {config_file} not found!")
            logger.info("Please ensure config.json exists in the current directory.")
            sys.exit(1)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in configuration file {config_file}: {e}")
            sys.exit(1)

        # Allow environment variables to override Telegram credentials
        telegram_cfg = config.setdefault('notifications', {}).setdefault('telegram', {})
        if os.environ.get('TELEGRAM_BOT_TOKEN'):
            telegram_cfg['bot_token'] = os.environ['TELEGRAM_BOT_TOKEN']
        if os.environ.get('TELEGRAM_CHAT_ID'):
            telegram_cfg['chat_id'] = os.environ['TELEGRAM_CHAT_ID']

        return config

    def init_database(self):
        """Initialize SQLite database for storing housing listings."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS housing_listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    residence_name TEXT NOT NULL,
                    address TEXT,
                    city TEXT,
                    region TEXT,
                    postal_code TEXT,
                    price REAL,
                    surface_area TEXT,
                    housing_type TEXT,
                    amenities TEXT,
                    description TEXT,
                    available_from DATE,
                    url TEXT,
                    listing_hash TEXT UNIQUE,
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE,
                    disappeared_at TIMESTAMP NULL,
                    crous_region TEXT
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS notifications_sent (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    listing_id INTEGER,
                    notification_type TEXT,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    success BOOLEAN,
                    error_message TEXT,
                    FOREIGN KEY (listing_id) REFERENCES housing_listings (id)
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS monitoring_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    url TEXT,
                    listings_found INTEGER,
                    new_listings INTEGER,
                    errors TEXT
                )
            ''')

            conn.commit()
        logger.info("Database initialized successfully")

    def store_listings(self, listings: List[Dict], crous_region: str) -> Tuple[List[Dict], List[Dict]]:
        """Store listings in database and return new ones and disappeared ones."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            new_listings = []

            # Mark all listings from this region as potentially disappeared
            cursor.execute(
                "UPDATE housing_listings SET is_active = FALSE WHERE crous_region = ? AND is_active = TRUE",
                (crous_region,)
            )

            for listing in listings:
                try:
                    # Add region info to listing
                    listing['crous_region'] = crous_region

                    # Check if listing already exists
                    cursor.execute(
                        "SELECT id, is_active FROM housing_listings WHERE listing_hash = ?",
                        (listing['listing_hash'],)
                    )
                    existing = cursor.fetchone()

                    if not existing:
                        # Insert new listing
                        cursor.execute('''
                            INSERT INTO housing_listings
                            (residence_name, address, city, region, postal_code, price, surface_area, housing_type, amenities, description, available_from, url, listing_hash, crous_region)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            listing.get('residence_name'),
                            listing.get('address'),
                            listing.get('city'),
                            listing.get('region'),
                            listing.get('postal_code'),
                            listing.get('price'),
                            listing.get('surface_area'),
                            listing.get('housing_type'),
                            listing.get('amenities'),
                            listing.get('description'),
                            listing.get('available_from'),
                            listing.get('url'),
                            listing['listing_hash'],
                            crous_region
                        ))

                        listing['id'] = cursor.lastrowid
                        new_listings.append(listing)
                        logger.info(f"🆕 New listing: {listing.get('residence_name')} - {listing.get('price', 'N/A')}€ - {crous_region}")
                    else:
                        # Update last_seen timestamp and mark as active
                        cursor.execute(
                            "UPDATE housing_listings SET last_seen = CURRENT_TIMESTAMP, is_active = TRUE, disappeared_at = NULL WHERE id = ?",
                            (existing[0],)
                        )

                except sqlite3.Error as e:
                    logger.error(f"Database error storing listing: {e}")
                    continue

            # Find disappeared listings (those that were active but not seen this cycle)
            grace_period_hours = self.config.get('filters', {}).get('disappearance_grace_period_hours', 2)
            cursor.execute('''
                SELECT id, residence_name, address, price, crous_region
                FROM housing_listings
                WHERE crous_region = ? AND is_active = FALSE AND disappeared_at IS NULL
                AND datetime('now', ?) > last_seen
            ''', (crous_region, f'-{grace_period_hours} hours'))

            disappeared_listings = []
            for row in cursor.fetchall():
                listing_id, residence_name, address, price, region = row
                disappeared_listings.append({
                    'id': listing_id,
                    'residence_name': residence_name,
                    'address': address,
                    'price': price,
                    'crous_region': region
                })

                # Mark as disappeared
                cursor.execute(
                    "UPDATE housing_listings SET disappeared_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (listing_id,)
                )
                logger.info(f"🚫 Disappeared listing: {residence_name} - {price}€ - {region}")

            conn.commit()
        return new_listings, disappeared_listings

    def log_monitoring_stats(self, url: str, total_found: int, new_found: int, errors: str = None):
        """Log monitoring statistics to database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO monitoring_stats (url, listings_found, new_listings, errors)
                VALUES (?, ?, ?, ?)
            ''', (url, total_found, new_found, errors))
            conn.commit()

    async def send_telegram_notification(self, listing: Dict) -> bool:
        """Send Telegram notification for new listing."""
        try:
            config = self.config['notifications']['telegram']
            if not config['enabled']:
                return False

            bot = Bot(token=config['bot_token'])

            # Format price
            price_str = f"{listing.get('price', 'N/A')}€/mois" if listing.get('price') else 'Prix non spécifié'

            message = f"""
🏠 **NOUVELLE CHAMBRE CROUS MARSEILLE!**

🏢 **Résidence**: {listing.get('residence_name', 'N/A')}
📍 **Adresse**: {listing.get('address', 'N/A')}
💰 **Prix**: {price_str}
📐 **Surface**: {listing.get('surface_area', 'N/A')}
🛏️ **Type**: {listing.get('housing_type', 'N/A')}
🔧 **Équipements**: {listing.get('amenities', 'N/A')}

🔗 **Lien**: {listing.get('url', 'N/A')}

⚡ Alerte envoyée à {datetime.now().strftime('%H:%M:%S')}
🚨 **AGISSEZ RAPIDEMENT!**
"""

            await bot.send_message(
                chat_id=config['chat_id'],
                text=message,
                parse_mode='Markdown',
                disable_web_page_preview=False
            )

            logger.info(f"✅ Telegram notification sent: {listing.get('residence_name')}")
            return True

        except Exception as e:
            logger.error(f"❌ Telegram notification failed: {e}")
            return False

    async def send_notifications(self, listing: Dict):
        """Send notifications through all enabled channels."""
        notification_results = []

        logger.info(f"🔔 Sending notifications for: {listing.get('residence_name')}")

        # Send Telegram notification (highest priority)
        telegram_success = await self.send_telegram_notification(listing)
        notification_results.append(('telegram', telegram_success))

        # Log notification results
        self.log_notifications(listing.get('id'), notification_results)

        # Summary
        successful = sum(1 for _, success in notification_results if success)
        logger.info(f"📊 Notifications sent: {successful}/{len(notification_results)} successful")

    async def send_disappearance_notification(self, listing: Dict) -> bool:
        """Send Telegram notification when a listing disappears."""
        try:
            config = self.config['notifications']['telegram']
            if not config['enabled']:
                return False

            bot = Bot(token=config['bot_token'])

            price_str = f"{listing.get('price', 'N/A')}€/mois" if listing.get('price') else 'Prix non spécifié'

            message = f"""
🚫 **LOGEMENT CROUS DISPARU**

🏢 **Résidence**: {listing.get('residence_name', 'N/A')}
📍 **Adresse**: {listing.get('address', 'N/A')}
💰 **Prix**: {price_str}

⏰ Disparu à {datetime.now().strftime('%H:%M:%S')}
"""

            await bot.send_message(
                chat_id=config['chat_id'],
                text=message,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )

            logger.info(f"✅ Disappearance notification sent: {listing.get('residence_name')}")
            return True

        except Exception as e:
            logger.error(f"❌ Disappearance notification failed: {e}")
            return False

    def get_crous_region_from_url(self, url: str) -> str:
        """Extract CROUS region from URL."""
        try:
            # Extract region code from URL like https://trouverunlogement.lescrous.fr/tools/41/search
            match = re.search(r'/tools/(\d+)/', url)
            if match:
                region_code = match.group(1)
                # Map region codes to names (approximate mapping)
                region_names = {
                    '11': 'Île-de-France',
                    '22': 'Centre-Val de Loire',
                    '24': 'Nouvelle-Aquitaine',
                    '27': 'Bourgogne-Franche-Comté',
                    '28': 'Normandie',
                    '32': 'Hauts-de-France',
                    '41': 'Provence-Alpes-Côte d\'Azur',
                    '44': 'Bretagne',
                    '52': 'Pays de la Loire',
                    '53': 'Grand Est',
                    '75': 'Paris',
                    '76': 'Occitanie',
                    '84': 'Auvergne-Rhône-Alpes',
                    '93': 'Corse',
                    '94': 'Outre-Mer'
                }
                return region_names.get(region_code, f'Région {region_code}')
        except Exception:
            pass
        return "Région inconnue"

    def log_notifications(self, listing_id: int, results: List[Tuple[str, bool]]):
        """Log notification results to database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for notification_type, success in results:
                cursor.execute('''
                    INSERT INTO notifications_sent (listing_id, notification_type, success)
                    VALUES (?, ?, ?)
                ''', (listing_id, notification_type, success))
            conn.commit()

    async def run_monitoring_cycle(self):
        """Run a complete monitoring cycle."""
        cycle_start = datetime.now()
        logger.info(f"🔍 Starting monitoring cycle at {cycle_start.strftime('%H:%M:%S')}")

        all_new_listings = []
        all_disappeared_listings = []
        total_listings_found = 0

        for url in self.config['scraping']['urls']:
            try:
                logger.info(f"🌐 Checking: {url}")

                # Use enhanced scraper
                listings = self.scraper.scrape_main_search_page(url)

                # Filter listings according to criteria
                filters = self.config.get('filters', {})
                filtered_listings = []
                for listing in listings:
                    if self.scraper.is_valid_listing(listing, filters):
                        filtered_listings.append(listing)

                total_listings_found += len(filtered_listings)
                crous_region = self.get_crous_region_from_url(url)
                new_listings, disappeared_listings = self.store_listings(filtered_listings, crous_region)
                all_new_listings.extend(new_listings)
                all_disappeared_listings.extend(disappeared_listings)

                # Log stats
                self.log_monitoring_stats(url, len(listings), len(new_listings))

                logger.info(f"📈 URL results: {len(listings)} total, {len(new_listings)} new")

                # Add delay between URL requests
                if len(self.config['scraping']['urls']) > 1:
                    await asyncio.sleep(3)

            except Exception as e:
                logger.error(f"❌ Error processing URL {url}: {e}")
                self.log_monitoring_stats(url, 0, 0, str(e))
                continue

        # Send notifications for new listings
        for listing in all_new_listings:
            try:
                # Send initial notification
                await self.send_notifications(listing)
                await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"❌ Error sending notifications for {listing.get('residence_name')}: {e}")

        # Send notifications for disappeared listings
        if self.config.get('filters', {}).get('notify_on_disappearance', False):
            for listing in all_disappeared_listings:
                try:
                    await self.send_disappearance_notification(listing)
                    await asyncio.sleep(1)  # Brief delay between notifications
                except Exception as e:
                    logger.error(f"❌ Error sending disappearance notification for {listing.get('residence_name')}: {e}")

        cycle_end = datetime.now()
        duration = (cycle_end - cycle_start).total_seconds()

        logger.info(f"✅ Cycle completed in {duration:.1f}s - Found {total_listings_found} total, {len(all_new_listings)} new, {len(all_disappeared_listings)} disappeared listings")

        if all_new_listings:
            logger.info("🎉 NEW LISTINGS FOUND! Check your notifications!")

        if all_disappeared_listings:
            logger.info("🚫 DISAPPEARED LISTINGS DETECTED! Check your notifications!")

        return len(all_new_listings)

    async def start_monitoring(self):
        """Start the monitoring system with scheduling."""
        logger.info("🚀 Starting CROUS Marseille Housing Monitor")
        self.print_status()

        interval = self.config.get('monitoring', {}).get('check_interval_seconds', 300)

        logger.info(f"⏰ Monitor scheduled to run every {interval} seconds")
        logger.info("📱 Notifications will be sent for new Marseille listings")
        logger.info("🛑 Press Ctrl+C to stop the monitor")

        try:
            while True:
                await self.run_monitoring_cycle()
                await asyncio.sleep(interval)
        except KeyboardInterrupt:
            logger.info("🛑 Monitor stopped by user")
            print("\n👋 CROUS Monitor stopped. Thanks for using the service!")
        except Exception as e:
            logger.error(f"💥 Unexpected error in monitoring loop: {e}")

    def print_status(self):
        """Print current monitoring status."""
        stats = self.get_monitoring_stats()

        print("\n" + "="*50)
        print("🏠 CROUS MARSEILLE MONITOR STATUS")
        print("="*50)
        print(f"📊 Total listings tracked: {stats['total_listings']}")
        print(f"🆕 New listings today: {stats['today_listings']}")
        print(f"🔔 Notifications sent today: {stats['today_notifications']}")
        print(f"🔍 Monitoring cycles today: {stats['today_cycles']}")
        print(f"⏰ Last check: {datetime.now().strftime('%H:%M:%S')}")

        # Check notification status
        enabled_notifications = []
        if self.config['notifications']['telegram']['enabled']:
            enabled_notifications.append('Telegram')

        print(f"🔔 Active notifications: {', '.join(enabled_notifications) if enabled_notifications else 'None'}")
        print("="*50)

    def get_monitoring_stats(self) -> Dict:
        """Get monitoring statistics from database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Total listings
            cursor.execute("SELECT COUNT(*) FROM housing_listings")
            total_listings = cursor.fetchone()[0]

            # New listings today
            cursor.execute("""
                SELECT COUNT(*) FROM housing_listings
                WHERE DATE(first_seen) = DATE('now')
            """)
            today_listings = cursor.fetchone()[0]

            # Successful notifications today
            cursor.execute("""
                SELECT COUNT(*) FROM notifications_sent
                WHERE DATE(sent_at) = DATE('now') AND success = 1
            """)
            today_notifications = cursor.fetchone()[0]

            # Recent monitoring cycles
            cursor.execute("""
                SELECT COUNT(*) FROM monitoring_stats
                WHERE DATE(timestamp) = DATE('now')
            """)
            today_cycles = cursor.fetchone()[0]

        return {
            'total_listings': total_listings,
            'today_listings': today_listings,
            'today_notifications': today_notifications,
            'today_cycles': today_cycles
        }

def main():
    """Main function to run the CROUS monitor."""
    print("🏠 CROUS Marseille Housing Monitor")
    print("=" * 40)

    # Check if config file exists
    if not os.path.exists('config.json'):
        print("❌ Configuration file 'config.json' not found!")
        print("📝 Please create and configure config.json before running the monitor.")
        return

    try:
        monitor = CROUSMonitorMain()

        # Check if running in service mode (via launchd or command line argument)
        service_mode = '--service' in sys.argv or 'LAUNCHD' in str(sys.argv)

        # Log configuration for debugging
        urls = monitor.config.get('scraping', {}).get('urls', [])
        logger.info(f"🤖 Service mode: {service_mode}")
        logger.info(f"📊 URLs configured: {len(urls)}")
        for i, url in enumerate(urls[:3], 1):
            logger.info(f"   URL {i}: {url}")
        if len(urls) > 3:
            logger.info(f"   ... and {len(urls) - 3} more URLs")

        if service_mode:
            print("🤖 Running in SERVICE MODE - Starting continuous monitoring...")
            asyncio.run(monitor.start_monitoring())
        else:
            # Interactive mode for testing
            # Run one test cycle
            print("🧪 Running initial test cycle...")
            new_listings = asyncio.run(monitor.run_monitoring_cycle())

            if new_listings > 0:
                print(f"🎉 Found {new_listings} new listings in test cycle!")
            else:
                print("ℹ️  No new listings found in test cycle (this is normal)")

            # Ask user if they want to start continuous monitoring
            print("\n" + "="*40)
            response = input("🤖 Start continuous monitoring? (y/n): ").lower().strip()

            if response in ['y', 'yes', 'oui']:
                asyncio.run(monitor.start_monitoring())
            else:
                print("⏸️  Monitor stopped. Run again when ready for continuous monitoring.")

    except Exception as e:
        logger.error(f"💥 Failed to start monitor: {e}")
        print(f"❌ Error: {e}")
        print("🔧 Please check your configuration and try again.")

if __name__ == "__main__":
    main()
