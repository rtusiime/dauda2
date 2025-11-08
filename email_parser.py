"""
Email Parser for Airbnb and Booking.com confirmation emails
Extracts: check-in date, check-out date, property identifier
"""

import re
from datetime import datetime
from dataclasses import dataclass
from typing import Optional
import email
from email import policy


@dataclass
class Booking:
    platform: str  # 'airbnb' or 'booking'
    checkin: datetime
    checkout: datetime
    property_id: Optional[str] = None
    guest_name: Optional[str] = None
    confirmation_code: Optional[str] = None


class EmailParser:
    
    # Common date patterns
    DATE_PATTERNS = [
        r'(?P<month>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(?P<day>\d{1,2}),?\s+(?P<year>\d{4})',
        r'(?P<day>\d{1,2})\s+(?P<month>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(?P<year>\d{4})',
        r'(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})',
        r'(?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<year>\d{4})',
    ]
    
    MONTH_MAP = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
    }

    def parse_email(self, email_content: str, email_subject: str = "") -> Optional[Booking]:
        """Main entry point - determines platform and extracts booking details"""
        
        # Detect platform
        email_lower = email_content.lower()
        subject_lower = email_subject.lower()
        
        if 'airbnb' in email_lower or 'airbnb' in subject_lower:
            return self._parse_airbnb(email_content, email_subject)
        elif 'booking.com' in email_lower or 'booking.com' in subject_lower:
            return self._parse_booking_com(email_content, email_subject)
        
        return None

    def _parse_airbnb(self, content: str, subject: str) -> Optional[Booking]:
        """Parse Airbnb confirmation email"""
        
        # Airbnb typically has patterns like:
        # "Check-in: Dec 15, 2025"
        # "Checkout: Dec 17, 2025"
        
        checkin = None
        checkout = None
        confirmation_code = None
        guest_name = None
        
        # Try to find check-in date
        checkin_patterns = [
            r'check[- ]?in[:\s]+(.+?)(?:\n|check|$)',
            r'arrives?[:\s]+(.+?)(?:\n|$)',
        ]
        
        for pattern in checkin_patterns:
            match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
            if match:
                date_str = match.group(1)
                checkin = self._extract_date(date_str)
                if checkin:
                    break
        
        # Try to find checkout date
        checkout_patterns = [
            r'check[- ]?out[:\s]+(.+?)(?:\n|check|$)',
            r'departs?[:\s]+(.+?)(?:\n|$)',
        ]
        
        for pattern in checkout_patterns:
            match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
            if match:
                date_str = match.group(1)
                checkout = self._extract_date(date_str)
                if checkout:
                    break
        
        # Extract confirmation code (typically HM followed by numbers)
        conf_match = re.search(r'confirmation[:\s]+([A-Z0-9]+)', content, re.IGNORECASE)
        if conf_match:
            confirmation_code = conf_match.group(1)
        
        # Extract guest name
        guest_match = re.search(r'guest[:\s]+([A-Z][a-z]+(?: [A-Z][a-z]+)?)', content, re.IGNORECASE)
        if guest_match:
            guest_name = guest_match.group(1)
        
        if checkin and checkout:
            return Booking(
                platform='airbnb',
                checkin=checkin,
                checkout=checkout,
                confirmation_code=confirmation_code,
                guest_name=guest_name
            )
        
        return None

    def _parse_booking_com(self, content: str, subject: str) -> Optional[Booking]:
        """Parse Booking.com confirmation email"""
        
        # Booking.com patterns:
        # "Check-in: Thursday, December 15, 2025"
        # "Check-out: Saturday, December 17, 2025"
        
        checkin = None
        checkout = None
        confirmation_code = None
        guest_name = None
        
        # Check-in patterns
        checkin_patterns = [
            r'check[- ]?in[:\s]+(?:.*?,\s*)?(.+?)(?:\n|from|$)',
            r'arrival[:\s]+(?:.*?,\s*)?(.+?)(?:\n|$)',
        ]
        
        for pattern in checkin_patterns:
            match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
            if match:
                date_str = match.group(1)
                checkin = self._extract_date(date_str)
                if checkin:
                    break
        
        # Checkout patterns
        checkout_patterns = [
            r'check[- ]?out[:\s]+(?:.*?,\s*)?(.+?)(?:\n|from|$)',
            r'departure[:\s]+(?:.*?,\s*)?(.+?)(?:\n|$)',
        ]
        
        for pattern in checkout_patterns:
            match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
            if match:
                date_str = match.group(1)
                checkout = self._extract_date(date_str)
                if checkout:
                    break
        
        # Booking.com confirmation code
        conf_match = re.search(r'booking(?:\s+number)?[:\s]+(\d+)', content, re.IGNORECASE)
        if conf_match:
            confirmation_code = conf_match.group(1)
        
        # Guest name from booking.com
        guest_match = re.search(r'(?:guest|name)[:\s]+([A-Z][a-z]+(?: [A-Z][a-z]+)?)', content, re.IGNORECASE)
        if guest_match:
            guest_name = guest_match.group(1)
        
        if checkin and checkout:
            return Booking(
                platform='booking',
                checkin=checkin,
                checkout=checkout,
                confirmation_code=confirmation_code,
                guest_name=guest_name
            )
        
        return None

    def _extract_date(self, date_str: str) -> Optional[datetime]:
        """Try all date patterns to extract a datetime object"""
        
        # Clean up the string
        date_str = date_str.strip()
        
        for pattern in self.DATE_PATTERNS:
            match = re.search(pattern, date_str, re.IGNORECASE)
            if match:
                groups = match.groupdict()
                
                # Convert month name to number if needed
                if not groups['month'].isdigit():
                    month = self.MONTH_MAP.get(groups['month'][:3].lower())
                else:
                    month = int(groups['month'])
                
                day = int(groups['day'])
                year = int(groups['year'])
                
                try:
                    return datetime(year, month, day)
                except ValueError:
                    continue
        
        return None


# Example usage
if __name__ == "__main__":
    parser = EmailParser()
    
    # Test with sample Airbnb email
    airbnb_sample = """
    You have a new reservation!
    
    Guest: John Smith
    Confirmation: HM123456789
    
    Check-in: Dec 15, 2025
    Checkout: Dec 17, 2025
    
    Property: Cozy Downtown Apartment
    """
    
    booking = parser.parse_email(airbnb_sample)
    if booking:
        print(f"✓ Parsed {booking.platform} booking")
        print(f"  Check-in: {booking.checkin.strftime('%Y-%m-%d')}")
        print(f"  Checkout: {booking.checkout.strftime('%Y-%m-%d')}")
        print(f"  Confirmation: {booking.confirmation_code}")
    
    # Test with Booking.com sample
    booking_com_sample = """
    Booking Confirmation
    
    Booking number: 9876543210
    Guest name: Jane Doe
    
    Check-in: Thursday, December 15, 2025
    Check-out: Saturday, December 17, 2025
    
    Property details: Riverside Loft
    """
    
    booking = parser.parse_email(booking_com_sample)
    if booking:
        print(f"\n✓ Parsed {booking.platform} booking")
        print(f"  Check-in: {booking.checkin.strftime('%Y-%m-%d')}")
        print(f"  Checkout: {booking.checkout.strftime('%Y-%m-%d')}")
        print(f"  Confirmation: {booking.confirmation_code}")
