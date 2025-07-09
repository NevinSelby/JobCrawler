import pandas as pd
import json
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# Specify the path to your JSON file
json_file_path = os.path.join(os.path.dirname(__file__), 'data', 'database.json') 

# Read the JSON file
try:
    with open(json_file_path, 'r') as file:
        json_data = json.load(file)
except FileNotFoundError:
    print(f"Error: File '{json_file_path}' not found.")
    exit()
except json.JSONDecodeError:
    print(f"Error: File '{json_file_path}' contains invalid JSON.")
    exit()

# Check if the JSON data is a list or a single record
if not isinstance(json_data, list):
    json_data = [json_data]  # Convert single record to list for consistent processing

# Load the Excel file
excel_file_path = os.path.join(os.path.dirname(__file__), 'data', 'uscis.xlsx')  # Replace with your actual path
try:
    excel_data = pd.read_excel(excel_file_path)
except FileNotFoundError:
    print(f"Error: Excel file '{excel_file_path}' not found.")
    exit()

excel_data.dropna(subset=['Employer (Petitioner) Name'], inplace=True)  # Drop rows with missing company names in Excel data

def is_entry_level_data_science_job(job_title):
    """Check if the job title matches entry-level data science/ML/analyst criteria."""
    title_lower = job_title.lower()
    
    # Entry-level indicators
    entry_level_keywords = [
        'entry level', 'junior', 'associate', 'new grad', 'graduate', 
        'fresher', 'trainee', 'intern', 'level 1', 'i ', ' i)', 'entry-level'
    ]
    
    # Data science/ML/analyst keywords
    role_keywords = [
        'data scientist', 'data science', 'data analyst', 'business analyst',
        'research analyst', 'machine learning', 'ml engineer', 'ai engineer',
        'analytics', 'statistician', 'quantitative analyst', 'insights analyst'
    ]
    
    # Exclude senior/experienced positions
    exclude_keywords = [
        'senior', 'sr.', 'lead', 'principal', 'director', 'manager', 'head of',
        '5+ years', '4+ years', '3+ years', 'experienced', 'expert'
    ]
    
    # Check if it's entry level OR has role keywords without exclusions
    has_entry_level = any(keyword in title_lower for keyword in entry_level_keywords)
    has_role_keyword = any(keyword in title_lower for keyword in role_keywords)
    has_exclusions = any(keyword in title_lower for keyword in exclude_keywords)
    
    # Job is relevant if it has role keywords and either entry-level indicators or no exclusions
    return has_role_keyword and (has_entry_level or not has_exclusions)

def send_batch_email_notification(matching_jobs, recipient_email):
    """Send a single email with all matching companies."""
    try:
        # Email settings
        sender_email = os.environ.get("SENDER_EMAIL")  # Replace with your Gmail
        sender_password = os.environ.get("SENDER_PASSWORD") 
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"Entry-Level Data Science Job Alert: {len(matching_jobs)} H-1B Sponsoring Companies"
        msg['From'] = sender_email
        msg['To'] = recipient_email
        
        # Create HTML content
        html = f"""
        <html>
          <head></head>
          <body>
            <h2>Entry-Level Data Science/ML/Analyst Opportunities at H-1B Sponsoring Companies</h2>
            <p>We found {len(matching_jobs)} entry-level data science, machine learning, and analyst positions at companies known to sponsor H-1B visas:</p>
            <table border="1" cellpadding="5">
              <tr>
                <th>Company</th>
                <th>Matched Company</th>
                <th>Job Title</th>
                <th>Match Score</th>
                <th>Location</th>
                <th>Link</th>
              </tr>
        """
        
        # Add each matching job to the email
        for job in matching_jobs:
            html += f"""
              <tr>
                <td>{job['company']}</td>
                <td>{job['matched_company']}</td>
                <td>{job['title']}</td>
                <td>{job['match_score']:.2f}</td>
                <td>{job['location']}</td>
                <td><a href="{job['url']}">View Job</a></td>
              </tr>
            """
            
        html += """
            </table>
            <p><em>Focus: Entry-level positions in Data Science, Machine Learning, and Analytics</em></p>
            <p>Date found: {}</p>
          </body>
        </html>
        """.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        # Attach HTML content
        msg.attach(MIMEText(html, 'html'))
        
        # Connect to server and send email
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        
        print(f"Email notification sent for {len(matching_jobs)} matching entry-level data science jobs")
        return True
    except Exception as e:
        print(f"Error sending email notification: {e}")
        return False

# Modified company matching code with improved filtering
matching_jobs = []  # To store all matching jobs

for record in json_data:
    # Skip if email already sent
    if record.get("email_sent", False):
        print(f"Skipping {record.get('company', 'Unknown')} - Email already sent")
        continue
    
    # Check if the job title is relevant for entry-level data science roles
    job_title = record.get('title', '')
    if not is_entry_level_data_science_job(job_title):
        print(f"Skipping job '{job_title}' - Not entry-level data science/ML/analyst role")
        continue
        
    print(f"Processing entry-level data science job: {job_title}")
    
    company_name = record.get("company", "Unknown Company")
    job_url = record.get("url", "")
    
    # Skip if company name is masked or unknown
    if not company_name or company_name in ["Unknown Company", "*********"] or all(c in '*' for c in company_name):
        print(f"Skipping job with masked/unknown company name: {company_name}")
        continue
    
    print(f"Processing company: {company_name}")
    
    # Create a list of all company names to compare
    all_companies = [company_name] + excel_data['Employer (Petitioner) Name'].tolist()
    
    # Initialize TF-IDF Vectorizer with improved parameters
    vectorizer = TfidfVectorizer(
        analyzer='char_wb', 
        ngram_range=(2, 4),  # Increased range for better matching
        lowercase=True,
        stop_words=None
    )
    
    try:
        # Compute TF-IDF matrix
        tfidf_matrix = vectorizer.fit_transform(all_companies)
        
        # Calculate cosine similarity
        cosine_similarities = np.dot(tfidf_matrix[0:1], tfidf_matrix[1:].T).toarray()[0]
        
        # Add similarity scores to a copy of the dataframe
        result_df = excel_data.copy()
        result_df['Similarity_Score'] = cosine_similarities

        # Set a threshold for considering a match (lowered for better recall)
        threshold = 0.5
        result_df['Is_Match'] = result_df['Similarity_Score'] >= threshold
        
        # Get matches above threshold
        matches = result_df[result_df['Is_Match']]
        
        # If there's at least one match, add to our matching jobs list
        if len(matches) > 0:
            best_match = matches.sort_values(by='Similarity_Score', ascending=False).iloc[0]
            print(f"Found match: {company_name} -> {best_match['Employer (Petitioner) Name']} (Score: {best_match['Similarity_Score']:.2f})")
            
            # Add to matching jobs list with all necessary info
            matching_jobs.append({
                'title': job_title,
                'company': company_name,
                'matched_company': best_match['Employer (Petitioner) Name'],
                'match_score': best_match['Similarity_Score'],
                'url': job_url,
                'location': record.get('location', 'Unknown Location')
            })

            print(f"Added to matching jobs: {job_title} at {company_name}")

            # Mark this record for email sent flag (will be updated later)
            record["email_sent"] = True
        else:
            print(f"No H-1B sponsoring company match found for: {company_name}")
            
    except Exception as e:
        print(f"Error processing company {company_name}: {e}")
        continue

# After processing all jobs, send a single email if we have matches
if matching_jobs:
    print(f"\nFound {len(matching_jobs)} entry-level data science/ML/analyst jobs at H-1B sponsoring companies")
    recipient_email = os.environ.get("RECIPIENT_EMAIL")  # Replace with recipient's email
    if send_batch_email_notification(matching_jobs, recipient_email):
        # Save updated database with email sent flags
        with open(json_file_path, 'w') as file:
            json.dump(json_data, file, indent=4)
            print(f"Updated job database with email sent flags")
    else:
        print("Failed to send email, not updating email_sent flags")
else:
    print("No matching entry-level data science/ML/analyst jobs found at H-1B sponsoring companies")
