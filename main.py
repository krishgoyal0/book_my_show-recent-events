import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import random

# ----------------------------
# Configuration
# ----------------------------
BASE_URL = "https://in.bookmyshow.com/explore/events-national-capital-region-ncr"
DATA_DIR = Path("data/bookmyshow")
DATA_DIR.mkdir(parents=True, exist_ok=True)
TIME_THRESHOLD = datetime.now() - timedelta(hours=24)
MAX_RETRIES = 3
WAIT_TIMEOUT = 45000  # 45 seconds
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
]
IGNORE_FIELDS = {'timestamp', 'scraped_at'}

# ----------------------------
# Helper Functions
# ----------------------------
def get_random_user_agent():
    return random.choice(USER_AGENTS)

def get_current_date() -> str:
    """Returns current date in YYYY-MM-DD format"""
    return datetime.now().strftime("%Y-%m-%d")

def get_yesterday_date() -> str:
    """Returns yesterday's date in YYYY-MM-DD format"""
    return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

def get_filename(date: str) -> Path:
    """Returns the filename for storing events data"""
    return DATA_DIR / f"events_{date}.json"

def is_recent_event(event_date_str: str) -> bool:
    """Check if event was added within our time threshold"""
    try:
        event_date = datetime.strptime(event_date_str, "%Y-%m-%d %H:%M:%S")
        return event_date >= TIME_THRESHOLD
    except (ValueError, TypeError):
        return False

# ----------------------------
# Scraping Functions
# ----------------------------
def scrape_events() -> Optional[List[Dict[str, Any]]]:
    """Scrape events from BookMyShow website"""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--user-agent=' + get_random_user_agent()
            ],
            slow_mo=100  # Add slight delay between actions
        )

        context = browser.new_context(
            user_agent=get_random_user_agent(),
            viewport={"width": 1280, "height": 720},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            java_script_enabled=True,
            has_touch=False,
            is_mobile=False
        )

        # Block unnecessary resources
        context.route("**/*.{png,jpg,jpeg,webp,gif,svg}", lambda route: route.abort())
        context.route("**/*.css", lambda route: route.abort())
        context.route("**/*.woff2", lambda route: route.abort())

        page = context.new_page()

        try:
            page.set_default_timeout(WAIT_TIMEOUT)
            print("Loading BookMyShow with realistic behavior...")
            page.goto(BASE_URL, wait_until="networkidle")

            # Human-like interactions
            for _ in range(3):
                page.mouse.move(
                    random.randint(0, 500),
                    random.randint(0, 500)
                )
                time.sleep(random.uniform(0.5, 1.5))

            # Dismiss popups
            for selector in [
                "button:has-text('Accept')",
                "button:has-text('Close')",
                "button:has-text('Got It')",
                "#onetrust-accept-btn-handler"
            ]:
                try:
                    page.click(selector, timeout=3000)
                    time.sleep(1)
                    break
                except:
                    pass

            # Scroll to load content
            print("Scrolling to load events...")
            for _ in range(5):
                page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
                time.sleep(random.uniform(1, 2.5))

            # Try multiple selector patterns
            event_selectors = [
                "div[class*='card']",
                "div[class*='event']",
                "a[href*='/events/']",
                "div[class*='slide']",
                "div[data-qa='event-card']",
                "div[class*='style__EventCardWrapper']"
            ]

            events = []
            for selector in event_selectors:
                try:
                    page.wait_for_selector(selector, timeout=10000)
                    cards = page.query_selector_all(selector)
                    print(f"Found {len(cards)} cards with selector: {selector}")

                    for card in cards:
                        try:
                            name = card.query_selector("h2, h3, h4, div[class*='title'], div[class*='name']")
                            if not name:
                                continue

                            event_data = {
                                "name": name.text_content().strip(),
                                "url": "https://in.bookmyshow.com" + card.get_attribute("href") if card.get_attribute("href") else "N/A",
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "scraped_at": datetime.now().isoformat()
                            }

                            # Extract additional details
                            details = {
                                "venue": "div[class*='venue'], div[class*='location']",
                                "date": "div[class*='date'], div[class*='time']",
                                "price": "div[class*='price'], span[class*='amount']",
                                "image": "img"
                            }
                            
                            for key, sel in details.items():
                                element = card.query_selector(sel)
                                if element:
                                    if key == "image":
                                        event_data[key] = element.get_attribute("src") or element.get_attribute("data-src") or "N/A"
                                    else:
                                        event_data[key] = element.text_content().strip()

                            events.append(event_data)
                        except Exception as e:
                            print(f"Error processing card: {e}")
                            continue

                    if events:
                        break

                except PlaywrightTimeoutError:
                    continue

            # Filter recent events
            recent_events = [e for e in events if is_recent_event(e['timestamp'])]
            return recent_events

        except Exception as e:
            print(f"Error during scraping: {str(e)}")
            return None
        finally:
            browser.close()

def save_events(events: List[Dict], date: str) -> None:
    """Save events to JSON file"""
    if not events:
        return
        
    filename = get_filename(date)
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(events)} events to {filename}")
    except Exception as e:
        print(f"Error saving events: {e}")

# ----------------------------
# Comparison Functions
# ----------------------------
def load_events(filename: str) -> Dict[str, Dict[str, Any]]:
    """Load events from JSON file and return as dict with url as keys."""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            events = json.load(f)
        return {event['url']: event for event in events}
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        print(f"Error: Could not decode {filename}")
        return {}

def compare_events(old_file: str, new_file: str) -> Dict[str, Any]:
    """Compare events between two JSON files and return differences."""
    # Load events from both files
    old_events = load_events(old_file)
    new_events = load_events(new_file)
    
    # Get all event URLs
    old_urls = set(old_events.keys())
    new_urls = set(new_events.keys())
    
    # Find added, removed, and modified events
    added_urls = new_urls - old_urls
    removed_urls = old_urls - new_urls
    
    modified_events = []
    for url in (old_urls & new_urls):
        old_event = old_events[url]
        new_event = new_events[url]
        
        changed_fields = {
            field: (old_event[field], new_event[field])
            for field in old_event
            if (field not in IGNORE_FIELDS and 
                field in new_event and 
                old_event[field] != new_event[field])
        }
        
        if changed_fields:
            modified_events.append({
                'url': url,
                'name': new_event.get('name', 'Untitled Event'),
                'changes': changed_fields
            })
    
    return {
        'added': [new_events[url] for url in added_urls],
        'removed': [old_events[url] for url in removed_urls],
        'modified': modified_events,
        'stats': {
            'added': len(added_urls),
            'removed': len(removed_urls),
            'modified': len(modified_events),
            'total_old': len(old_events),
            'total_new': len(new_events)
        }
    }

def print_comparison_results(results: Dict[str, Any]) -> None:
    """Print the comparison results in a readable format."""
    stats = results['stats']
    
    print("\n=== Event Comparison Results ===")
    print(f"Old file: {stats['total_old']} events")
    print(f"New file: {stats['total_new']} events")
    print(f"Comparison time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    print(f"Newly added events ({stats['added']}):")
    for event in results['added']:
        print(f"- {event.get('name', 'Untitled Event')}")
        print(f"  URL: {event.get('url', 'N/A')}")
        if event.get('is_fast_filling', False):
            print("  (Fast Filling!)")
    
    print(f"\nRemoved events ({stats['removed']}):")
    for event in results['removed']:
        print(f"- {event.get('name', 'Untitled Event')}")
        print(f"  URL: {event.get('url', 'N/A')}")
    
    print(f"\nModified events ({stats['modified']}):")
    for event in results['modified']:
        print(f"\n- {event['name']}")
        print(f"  URL: {event['url']}")
        for field, (old_val, new_val) in event['changes'].items():
            print(f"  Changed {field}:")
            print(f"    Old: {old_val}")
            print(f"    New: {new_val}")

# ----------------------------
# Main Execution
# ----------------------------
def main():
    # Step 1: Scrape today's events
    current_date = get_current_date()
    yesterday_date = get_yesterday_date()
    
    print(f"Scraping BookMyShow NCR events (recent since {TIME_THRESHOLD})...")
    recent_events = scrape_events()
    
    if not recent_events:
        print("No recent events found or scraping failed.")
        return
    
    # Step 2: Save today's events
    save_events(recent_events, current_date)
    
    # Step 3: Compare with yesterday's events
    today_file = get_filename(current_date)
    yesterday_file = get_filename(yesterday_date)
    
    if not yesterday_file.exists():
        print("\nNo previous day's file found for comparison.")
        return
    
    print("\nComparing with previous day's events...")
    comparison_results = compare_events(yesterday_file, today_file)
    print_comparison_results(comparison_results)
    
    # Print summary of new events
    if comparison_results['added']:
        print("\n=== New Events Summary ===")
        for i, event in enumerate(comparison_results['added'][:10], 1):
            print(f"\n{i}. {event.get('name', 'Untitled Event')}")
            print(f"   Venue: {event.get('venue', 'N/A')}")
            print(f"   Date: {event.get('date', 'N/A')}")
            print(f"   URL: {event.get('url', 'N/A')}")
            if event.get('price'):
                print(f"   Price: {event.get('price')}")

if __name__ == "__main__":
    main()