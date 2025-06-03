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
REPORTS_DIR = Path("reports")
DATA_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
TIME_THRESHOLD = datetime.now() - timedelta(hours=24)
MAX_RETRIES = 3
WAIT_TIMEOUT = 60000  # Increased to 60 seconds
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
]
IGNORE_FIELDS = {'timestamp', 'scraped_at'}
STATUS_INDICATORS = {
    'fast_filling': ['fast filling', 'filling fast', 'almost full', 'limited seats'],
    'sold_out': ['sold out', 'housefull', 'no seats']
}

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

def get_report_filename(date: str) -> Path:
    """Returns the filename for storing report"""
    return REPORTS_DIR / f"event_report_{date}.txt"

def is_recent_event(event_date_str: str) -> bool:
    """Check if event was added within our time threshold"""
    try:
        event_date = datetime.strptime(event_date_str, "%Y-%m-%d %H:%M:%S")
        return event_date >= TIME_THRESHOLD
    except (ValueError, TypeError):
        return False

def check_event_status(text: str) -> Dict[str, bool]:
    """Check if event is fast filling or sold out based on text"""
    text = text.lower()
    return {
        'is_fast_filling': any(indicator in text for indicator in STATUS_INDICATORS['fast_filling']),
        'is_sold_out': any(indicator in text for indicator in STATUS_INDICATORS['sold_out'])
    }

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
            slow_mo=200  # Increased delay between actions
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
            for _ in range(5):  # Increased interactions
                page.mouse.move(
                    random.randint(0, 500),
                    random.randint(0, 500)
                )
                time.sleep(random.uniform(0.5, 2.0))  # Increased delay

            # Dismiss popups
            for selector in [
                "button:has-text('Accept')",
                "button:has-text('Close')",
                "button:has-text('Got It')",
                "#onetrust-accept-btn-handler"
            ]:
                try:
                    page.click(selector, timeout=5000)  # Increased timeout
                    time.sleep(1.5)  # Increased delay
                    break
                except:
                    pass

            # Scroll to load content with more attempts and longer delays
            print("Scrolling to load events...")
            scroll_attempts = 8  # Increased from 5 to 8
            scroll_delay_min = 1.5  # Increased minimum delay
            scroll_delay_max = 3.5  # Increased maximum delay
            
            for i in range(scroll_attempts):
                # Scroll a bit further down each time
                scroll_distance = f"window.innerHeight * {0.8 + (i * 0.1)}"
                page.evaluate(f"window.scrollBy(0, {scroll_distance})")
                print(f"Scroll attempt {i+1}/{scroll_attempts}")
                time.sleep(random.uniform(scroll_delay_min, scroll_delay_max))
                
                # Check for loading indicators
                try:
                    loading_selector = "div[class*='loading'], div[class*='spinner']"
                    page.wait_for_selector(loading_selector, state="hidden", timeout=5000)
                except:
                    pass

            # Wait for content to settle after scrolling
            time.sleep(3)

            # Try multiple selector patterns with more variations
            event_selectors = [
                "div[class*='card']",
                "div[class*='event']",
                "a[href*='/events/']",
                "div[class*='slide']",
                "div[data-qa='event-card']",
                "div[class*='style__EventCardWrapper']",
                "div[class*='event-card']",
                "div[class*='card-container']",
                "div[class*='event-container']"
            ]

            events = []
            seen_urls = set()
            
            for selector in event_selectors:
                try:
                    page.wait_for_selector(selector, timeout=15000)  # Increased timeout
                    cards = page.query_selector_all(selector)
                    print(f"Found {len(cards)} cards with selector: {selector}")

                    for card in cards:
                        try:
                            name = card.query_selector("h2, h3, h4, div[class*='title'], div[class*='name'], span[class*='title']")
                            if not name:
                                continue

                            url = " " + card.get_attribute("href") if card.get_attribute("href") else "N/A"
                            
                            # Skip duplicates
                            if url in seen_urls:
                                continue
                            seen_urls.add(url)

                            event_data = {
                                "name": name.text_content().strip(),
                                "url": url,
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "scraped_at": datetime.now().isoformat()
                            }

                            # Extract additional details with more selectors
                            details = {
                                "venue": "div[class*='venue'], div[class*='location'], span[class*='venue'], span[class*='location']",
                                "date": "div[class*='date'], div[class*='time'], span[class*='date'], span[class*='time']",
                                "price": "div[class*='price'], span[class*='amount'], div[class*='cost'], span[class*='price']",
                                "image": "img",
                                "status": "div[class*='status'], div[class*='tag'], span[class*='ribbon'], div[class*='label']"
                            }
                            
                            for key, sel in details.items():
                                try:
                                    element = card.query_selector(sel)
                                    if element:
                                        if key == "image":
                                            event_data[key] = element.get_attribute("src") or element.get_attribute("data-src") or "N/A"
                                        else:
                                            text_content = element.text_content().strip()
                                            event_data[key] = text_content
                                            
                                            # Check for fast filling or sold out status
                                            if key == "status":
                                                status_info = check_event_status(text_content)
                                                event_data.update(status_info)
                                except:
                                    pass

                            events.append(event_data)
                        except Exception as e:
                            print(f"Error processing card: {e}")
                            continue

                    if events:
                        print(f"Successfully collected {len(events)} events with selector: {selector}")
                        break

                except PlaywrightTimeoutError:
                    continue

            # Filter recent events
            recent_events = [e for e in events if is_recent_event(e['timestamp'])]
            print(f"Found {len(recent_events)} recent events")
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
    
    return {
        'added': [new_events[url] for url in added_urls],
        'removed': [old_events[url] for url in removed_urls],
        'stats': {
            'added': len(added_urls),
            'removed': len(removed_urls),
            'total_old': len(old_events),
            'total_new': len(new_events)
        }
    }

def generate_report_content(results: Dict[str, Any]) -> str:
    """Generate the report content as a string."""
    stats = results['stats']
    report_lines = []
    
    report_lines.append("\n=== Event Comparison Results ===")
    report_lines.append(f"Old file: {stats['total_old']} events")
    report_lines.append(f"New file: {stats['total_new']} events")
    report_lines.append(f"Comparison time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    report_lines.append(f"Newly added events ({stats['added']}):")
    for event in results['added']:
        report_lines.append(f"- {event.get('name', 'Untitled Event')}")
        report_lines.append(f"  URL: {event.get('url', 'N/A')}")
        if event.get('is_fast_filling', False):
            report_lines.append("  (Fast Filling!)")
        if event.get('is_sold_out', False):
            report_lines.append("  (SOLD OUT!)")
    
    report_lines.append(f"\nRemoved events ({stats['removed']}):")
    for event in results['removed']:
        report_lines.append(f"- {event.get('name', 'Untitled Event')}")
        report_lines.append(f"  URL: {event.get('url', 'N/A')}")
    
    # Add summary of new events
    if results['added']:
        report_lines.append("\n=== New Events Summary ===")
        for i, event in enumerate(results['added'][:10], 1):
            report_lines.append(f"\n{i}. {event.get('name', 'Untitled Event')}")
            report_lines.append(f"   Venue: {event.get('venue', 'N/A')}")
            report_lines.append(f"   Date: {event.get('date', 'N/A')}")
            report_lines.append(f"   URL: {event.get('url', 'N/A')}")
            if event.get('price'):
                report_lines.append(f"   Price: {event.get('price')}")
            if event.get('is_fast_filling', False):
                report_lines.append("   Status: FAST FILLING!")
            if event.get('is_sold_out', False):
                report_lines.append("   Status: SOLD OUT!")
    
    return "\n".join(report_lines)

def save_report(report_content: str, date: str) -> None:
    """Save the report to a text file."""
    filename = get_report_filename(date)
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(report_content)
        print(f"\nReport saved to {filename}")
    except Exception as e:
        print(f"Error saving report: {e}")

def print_and_save_report(results: Dict[str, Any], date: str) -> None:
    """Print the report to console and save to file."""
    report_content = generate_report_content(results)
    
    # Print to console
    print(report_content)
    
    # Save to file
    save_report(report_content, date)

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
    print_and_save_report(comparison_results, current_date)

if __name__ == "__main__":
    main()