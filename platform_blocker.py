"""
Platform Blocker - Uses Playwright to automate date blocking
on Airbnb and Booking.com web interfaces
"""

from playwright.async_api import async_playwright, Page, Browser
from datetime import datetime, timedelta
from typing import Optional, List
import asyncio
import os


class PlatformBlocker:
    """Handles automated blocking of dates on vacation rental platforms"""
    
    def __init__(self, credentials_path: str = "credentials.json"):
        self.credentials = self._load_credentials(credentials_path)
        self.browser: Optional[Browser] = None
        
    def _load_credentials(self, path: str) -> dict:
        """Load platform credentials from secure storage"""
        import json
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            # For now, use environment variables
            return {
                'airbnb': {
                    'email': os.getenv('AIRBNB_EMAIL', ''),
                    'password': os.getenv('AIRBNB_PASSWORD', ''),
                },
                'booking': {
                    'email': os.getenv('BOOKING_EMAIL', ''),
                    'password': os.getenv('BOOKING_PASSWORD', ''),
                }
            }

    async def block_dates(self, platform: str, checkin: datetime, 
                         checkout: datetime, property_id: Optional[str] = None) -> bool:
        """
        Main entry point - blocks dates on specified platform
        
        Args:
            platform: 'airbnb' or 'booking'
            checkin: First night to block
            checkout: Day after last night
            property_id: Optional property identifier
            
        Returns:
            True if successful, False otherwise
        """
        
        async with async_playwright() as p:
            # Launch browser (headless for production, headed for debugging)
            self.browser = await p.chromium.launch(
                headless=os.getenv('HEADLESS', 'true').lower() == 'true'
            )
            
            context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()
            
            try:
                if platform == 'airbnb':
                    success = await self._block_airbnb(page, checkin, checkout, property_id)
                elif platform == 'booking':
                    success = await self._block_booking(page, checkin, checkout, property_id)
                else:
                    print(f"Unknown platform: {platform}")
                    success = False
                    
                return success
                
            except Exception as e:
                print(f"Error blocking dates on {platform}: {e}")
                # Save screenshot for debugging
                await page.screenshot(path=f"error_{platform}_{int(datetime.now().timestamp())}.png")
                return False
                
            finally:
                await self.browser.close()

    async def _block_airbnb(self, page: Page, checkin: datetime, 
                           checkout: datetime, property_id: Optional[str] = None) -> bool:
        """Block dates on Airbnb calendar"""
        
        print(f"🔒 Blocking Airbnb: {checkin.date()} to {checkout.date()}")
        
        # Step 1: Login
        await page.goto('https://www.airbnb.com/login')
        await page.wait_for_load_state('networkidle')
        
        # Handle cookie consent if present
        try:
            await page.click('button:has-text("Accept")', timeout=3000)
        except:
            pass
        
        # Fill login form
        await page.fill('input[type="email"]', self.credentials['airbnb']['email'])
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(1000)
        
        await page.fill('input[type="password"]', self.credentials['airbnb']['password'])
        await page.click('button[type="submit"]')
        
        # Wait for login to complete
        await page.wait_for_url('**/hosting**', timeout=30000)
        print("✓ Logged into Airbnb")
        
        # Step 2: Navigate to calendar
        await page.goto('https://www.airbnb.com/hosting/calendar')
        await page.wait_for_load_state('networkidle')
        
        # If specific property, select it
        if property_id:
            try:
                await page.click(f'[data-listing-id="{property_id}"]', timeout=5000)
                await page.wait_for_timeout(1000)
            except:
                print(f"⚠ Could not find property {property_id}, using first available")
        
        # Step 3: Block dates
        # Navigate to the month of check-in
        target_month = checkin.strftime('%B %Y')
        
        # Click next month button until we reach target month
        max_clicks = 24  # Don't infinite loop
        for _ in range(max_clicks):
            current_month = await page.text_content('.calendar-month-header')
            if target_month.lower() in current_month.lower():
                break
            await page.click('[aria-label*="Next"]')
            await page.wait_for_timeout(500)
        
        print(f"✓ Navigated to {target_month}")
        
        # Step 4: Select date range
        # Click on check-in date
        checkin_selector = f'td[data-testid*="{checkin.strftime("%Y-%m-%d")}"]'
        await page.click(checkin_selector)
        await page.wait_for_timeout(300)
        
        # Click on checkout date (or day before checkout)
        last_night = checkout - timedelta(days=1)
        checkout_selector = f'td[data-testid*="{last_night.strftime("%Y-%m-%d")}"]'
        await page.click(checkout_selector)
        await page.wait_for_timeout(500)
        
        print(f"✓ Selected dates: {checkin.date()} to {last_night.date()}")
        
        # Step 5: Block the dates
        # Look for "Block dates" or "Mark as unavailable" button
        try:
            await page.click('button:has-text("Block")', timeout=3000)
        except:
            try:
                await page.click('button:has-text("Unavailable")', timeout=3000)
            except:
                # Try right-click context menu approach
                await page.click(checkin_selector, button='right')
                await page.click('text="Block dates"')
        
        await page.wait_for_timeout(1000)
        
        # Confirm if there's a modal
        try:
            await page.click('button:has-text("Save")', timeout=2000)
        except:
            pass
        
        print("✓ Dates blocked on Airbnb")
        return True

    async def _block_booking(self, page: Page, checkin: datetime, 
                            checkout: datetime, property_id: Optional[str] = None) -> bool:
        """Block dates on Booking.com Extranet"""
        
        print(f"🔒 Blocking Booking.com: {checkin.date()} to {checkout.date()}")
        
        # Step 1: Login to Extranet
        await page.goto('https://admin.booking.com/hotel/hoteladmin/login.html')
        await page.wait_for_load_state('networkidle')
        
        # Fill login
        await page.fill('input[name="loginname"]', self.credentials['booking']['email'])
        await page.fill('input[name="password"]', self.credentials['booking']['password'])
        await page.click('button[type="submit"]')
        
        # Wait for dashboard
        await page.wait_for_url('**/extranet/**', timeout=30000)
        print("✓ Logged into Booking.com")
        
        # Step 2: Navigate to calendar
        await page.goto('https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/calendar.html')
        await page.wait_for_load_state('networkidle')
        
        # Select property if needed
        if property_id:
            try:
                await page.select_option('select[name="hotel_id"]', property_id)
                await page.wait_for_timeout(1000)
            except:
                print(f"⚠ Could not select property {property_id}")
        
        # Step 3: Navigate to correct month
        target_month = checkin.strftime('%B %Y')
        
        for _ in range(24):
            try:
                current_month = await page.text_content('.calendar-current-month')
                if target_month.lower() in current_month.lower():
                    break
                await page.click('[data-action="calendar-next-month"]')
                await page.wait_for_timeout(500)
            except:
                break
        
        print(f"✓ Navigated to {target_month}")
        
        # Step 4: Block dates
        # Booking.com typically has a different UX - select dates then click "Close"
        current_date = checkin
        blocked_dates = []
        
        while current_date < checkout:
            date_str = current_date.strftime('%Y-%m-%d')
            date_cell = f'td[data-date="{date_str}"]'
            
            try:
                # Click on the date cell
                await page.click(date_cell)
                blocked_dates.append(date_str)
                await page.wait_for_timeout(200)
            except:
                print(f"⚠ Could not click date: {date_str}")
            
            current_date += timedelta(days=1)
        
        print(f"✓ Selected {len(blocked_dates)} dates")
        
        # Step 5: Apply the closure
        try:
            # Look for "Close dates" or "Make unavailable" button
            await page.click('button:has-text("Close")', timeout=3000)
        except:
            try:
                await page.click('button:has-text("Unavailable")', timeout=3000)
            except:
                await page.click('button.availability-close')
        
        await page.wait_for_timeout(1000)
        
        # Confirm if needed
        try:
            await page.click('button:has-text("Confirm")', timeout=2000)
        except:
            pass
        
        print("✓ Dates blocked on Booking.com")
        return True


async def test_blocker():
    """Test the blocker with sample dates"""
    blocker = PlatformBlocker()
    
    # Test dates (3 days from now)
    checkin = datetime.now() + timedelta(days=3)
    checkout = checkin + timedelta(days=2)
    
    print("\n" + "="*60)
    print("TESTING PLATFORM BLOCKER")
    print("="*60)
    
    # Test Airbnb
    success = await blocker.block_dates('airbnb', checkin, checkout)
    print(f"\nAirbnb blocking: {'✓ SUCCESS' if success else '✗ FAILED'}")
    
    # Test Booking.com
    success = await blocker.block_dates('booking', checkin, checkout)
    print(f"Booking.com blocking: {'✓ SUCCESS' if success else '✗ FAILED'}")


if __name__ == "__main__":
    # Set to False to see the browser for debugging
    os.environ['HEADLESS'] = 'false'
    
    asyncio.run(test_blocker())
