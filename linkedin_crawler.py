import requests
from bs4 import BeautifulSoup
import json
import os
import time
import random
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from pathlib import Path


class LinkedInJobCrawler:
    def __init__(self, config_file=None):
        """Initialize the LinkedIn job crawler with configuration."""
        # Create base directory path
        base_dir = Path.cwd() / "data" 
        
        # Create directory if it doesn't exist
        os.makedirs(base_dir, exist_ok=True)
        
        # Set file paths
        if config_file is None:
            config_file = base_dir / "carwler.json"
        
        database_path = base_dir / "database.json"
        
        # Default configuration for entry-level data science/ML/analyst roles
        self.config = {
            'job_url': 'https://www.linkedin.com/jobs/search/?f_TPR=r3600&f_E=1%2C2&keywords=data%20science%20entry%20level%20OR%20data%20analyst%20junior%20OR%20ML%20engineer%20new%20grad',
            'keywords': ['data science', 'data scientist', 'data analyst', 'machine learning', 'ml engineer', 'business analyst', 'research analyst', 'junior', 'entry level', 'new grad', 'associate', 'python', 'sql', 'analytics'],
            'excluded_keywords': ['senior', 'lead', 'principal', 'director', 'manager', '5+ years', '4+ years', '3+ years', 'experienced'],
            'database_file': str(database_path),
            'user_agents': [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0'
            ],
            'request_delay': {
                'min_seconds': 3,
                'max_seconds': 7
            }
        }
        
        # Convert config_file to string if it's a Path object
        config_file = str(config_file)
        
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                custom_config = json.load(f)
                self.config.update(custom_config)
        else:
            # Create parent directory if it doesn't exist
            os.makedirs(os.path.dirname(config_file), exist_ok=True)
            # Save default configuration
            with open(config_file, 'w') as f:
                json.dump(self.config, f, indent=4)
                
        # Initialize the webdriver
        self.driver = None
        
        # Load previous jobs
        self.previous_jobs = self.load_previous_jobs()

        
    def setup_driver(self):
        """Set up Selenium WebDriver with enhanced anti-detection measures."""
        if self.driver is not None:
            try:
                self.driver.quit()
            except:
                pass
                
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Add random user agent
        user_agent = random.choice(self.config['user_agents'])
        chrome_options.add_argument(f"--user-agent={user_agent}")
        
        try:
            self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        except Exception as e:
            print(f"Error setting up Chrome driver: {e}")
            print("Trying with direct ChromeDriver...")
            self.driver = webdriver.Chrome(options=chrome_options)
        
        # Execute script to hide automation indicators
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
    def load_previous_jobs(self):
        """Load previously scraped jobs from database file."""
        if not os.path.exists(self.config['database_file']):
            return []
        try:
            with open(self.config['database_file'], 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading previous jobs: {e}")
            return []
            
    def save_jobs(self, jobs):
        """Save jobs to the database file."""
        try:
            with open(self.config['database_file'], 'w') as f:
                json.dump(jobs, f, indent=4)
            print(f"Jobs saved to {self.config['database_file']}")
        except Exception as e:
            print(f"Error saving jobs: {e}")
            
    def is_new_job(self, job):
        """Check if a job is new by comparing with previous jobs."""
        for prev_job in self.previous_jobs:
            # Compare key fields to determine if it's the same job
            if (job['title'] == prev_job['title'] and 
                job['company'] == prev_job['company'] and
                job['location'] == prev_job['location']):
                return False
        return True
        
    def is_job_relevant(self, job_title):
        """Check if job title contains desired keywords and not excluded keywords."""
        title_lower = job_title.lower()
        
        # Check if any keyword is in the title
        has_keyword = any(keyword.lower() in title_lower for keyword in self.config['keywords'])
        
        # Check if any excluded keyword is in the title
        has_excluded = any(keyword.lower() in title_lower for keyword in self.config['excluded_keywords'])
        
        return has_keyword and not has_excluded
        
    def extract_text_safely(self, element):
        """Safely extract text from an element, handling various text obfuscation methods."""
        if not element:
            return None
            
        # Try different methods to get text
        text_methods = [
            lambda e: e.get_text(strip=True),
            lambda e: e.text.strip(),
            lambda e: e.get('title', '').strip(),
            lambda e: e.get('aria-label', '').strip()
        ]
        
        for method in text_methods:
            try:
                text = method(element)
                if text and text != '' and not all(c in '*' for c in text):
                    return text
            except:
                continue
        
        return None
        
    def scrape_linkedin_jobs(self):
        """Scrape job data from LinkedIn with improved extraction methods."""
        jobs = []
        try:
            if self.driver is None:
                self.setup_driver()
                
            print(f"Fetching LinkedIn jobs from: {self.config['job_url']}")
            self.driver.get(self.config['job_url'])
            
            # Random delay to mimic human behavior
            time.sleep(random.uniform(5, 8))
            
            # Scroll down to load more results (LinkedIn uses infinite scroll)
            print("Scrolling to load more job listings...")
            scroll_count = 0
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            
            while scroll_count < 3:  # Reduced scrolling to avoid detection
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(random.uniform(2, 4))
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
                scroll_count += 1
                
            # Get the page source after JavaScript execution
            html = self.driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            
            # Try multiple selectors for LinkedIn job cards
            job_selectors = [
                'div.base-card',
                'div.job-search-card',
                'div[data-entity-urn*="job"]',
                'li.result-card',
                'div.base-search-card'
            ]
            
            job_cards = []
            for selector in job_selectors:
                job_cards = soup.select(selector)
                if job_cards:
                    print(f"Found {len(job_cards)} job cards using selector: {selector}")
                    break
            
            if not job_cards:
                print("No job cards found with any selector")
                return jobs
            
            for card in job_cards:
                try:
                    # Try multiple selectors for job title
                    title_selectors = [
                        'h3.base-search-card__title',
                        'h3.job-search-card__title', 
                        'a[data-tracking-control-name="public_jobs_jserp-result_search-card"]',
                        '.job-search-card__title a',
                        'h3 a'
                    ]
                    
                    title = None
                    title_element = None
                    for selector in title_selectors:
                        title_element = card.select_one(selector)
                        if title_element:
                            title = self.extract_text_safely(title_element)
                            if title:
                                break
                    
                    if not title or title == "Unknown Title":
                        continue
                    
                    if not self.is_job_relevant(title):
                        continue
                        
                    # Try multiple selectors for company name
                    company_selectors = [
                        'h4.base-search-card__subtitle',
                        'h4.job-search-card__subtitle',
                        '.job-search-card__subtitle-link',
                        'a[data-tracking-control-name="public_jobs_jserp-result_job-search-card-subtitle"]',
                        '.base-search-card__subtitle a'
                    ]
                    
                    company = None
                    for selector in company_selectors:
                        company_element = card.select_one(selector)
                        if company_element:
                            company = self.extract_text_safely(company_element)
                            if company:
                                break
                    
                    if not company:
                        company = "Unknown Company"
                    
                    # Try multiple selectors for location
                    location_selectors = [
                        'span.job-search-card__location',
                        '.job-search-card__location',
                        '.base-search-card__metadata span',
                        'span[data-tracking-control-name="public_jobs_jserp-result_job-search-card-location"]'
                    ]
                    
                    location = None
                    for selector in location_selectors:
                        location_element = card.select_one(selector)
                        if location_element:
                            location = self.extract_text_safely(location_element)
                            if location:
                                break
                    
                    if not location:
                        location = "Unknown Location"
                    
                    # Extract job URL
                    link_selectors = [
                        'a.base-card__full-link',
                        'h3 a',
                        'a[data-tracking-control-name="public_jobs_jserp-result_search-card"]'
                    ]
                    
                    job_url = ""
                    for selector in link_selectors:
                        link_element = card.select_one(selector)
                        if link_element and link_element.get('href'):
                            job_url = link_element['href']
                            if not job_url.startswith('http'):
                                job_url = 'https://www.linkedin.com' + job_url
                            break
                    
                    # Extract posting date
                    date_selectors = [
                        'time.job-search-card__listdate',
                        'time',
                        '.job-search-card__listdate'
                    ]
                    
                    date_posted = "Recent"
                    for selector in date_selectors:
                        date_element = card.select_one(selector)
                        if date_element:
                            date_text = self.extract_text_safely(date_element)
                            if date_text:
                                date_posted = date_text
                                break
                    
                    # Only add if we have meaningful data
                    if job_url and title != "Unknown Title":
                        jobs.append({
                            'title': title,
                            'company': company,
                            'location': location,
                            'date_posted': date_posted,
                            'url': job_url,
                            'source': 'LinkedIn',
                            'scraped_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
                        print(f"Found job: {title} at {company}")
                        
                except Exception as e:
                    print(f"Error extracting job data: {e}")
                    continue
            
        except Exception as e:
            print(f"Error scraping LinkedIn: {e}")
            # Try to restart the driver if it failed
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
            
        return jobs
        
    def run_once(self):
        """Run the LinkedIn job crawler once."""
        print(f"Starting LinkedIn job scraping at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Looking for entry-level data science/ML/analyst jobs posted in the last 24 hours")
        
        # Scrape LinkedIn jobs
        current_jobs = self.scrape_linkedin_jobs()
        
        # Identify new jobs
        new_jobs = []
        for job in current_jobs:
            if self.is_new_job(job):
                job['email_sent'] = False
                new_jobs.append(job)
        

        one_hour_ago = datetime.now() - timedelta(hours=1)
        filtered_previous_jobs = [
            job for job in self.previous_jobs 
            if datetime.strptime(job['scraped_date'], '%Y-%m-%d %H:%M:%S') >= one_hour_ago
]
        all_jobs = filtered_previous_jobs + new_jobs
        self.save_jobs(all_jobs)
        
        print(f"\nFound {len(current_jobs)} total job listings")
        print(f"Identified {len(new_jobs)} new job postings")
        
        return new_jobs
        
    def cleanup(self):
        """Clean up resources."""
        if self.driver:
            try:
                self.driver.quit()
                print("Browser closed successfully")
            except:
                pass
            self.driver = None



# Run the LinkedIn crawler once
if __name__ == "__main__":
    try:
        print("=== LinkedIn Job Crawler - Entry-Level Data Science/ML/Analyst Jobs ===")
        crawler = LinkedInJobCrawler()
        new_jobs = crawler.run_once()
        
        # Print a summary of results
        if new_jobs:
            print("\n===== NEW JOBS FOUND =====")
            for i, job in enumerate(new_jobs, 1):
                print(f"{i}. {job['title']} at {job['company']}")
                print(f"   Location: {job['location']}")
                print(f"   Posted: {job['date_posted']}")
                print(f"   URL: {job['url']}")
                print()
        else:
            print("\nNo new entry-level data science/ML/analyst jobs found on LinkedIn in the last 24 hours.")
            
    except KeyboardInterrupt:
        print("\nJob crawler stopped by user")
    except Exception as e:
        print(f"\nError in job crawler: {e}")
    finally:
        # Clean up resources
        if 'crawler' in locals():
            crawler.cleanup()


