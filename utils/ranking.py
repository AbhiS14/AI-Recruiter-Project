import re

def rank_resume(job_desc, resume_keywords):
    # Extract words from job description using regex
    job_keywords = set(re.findall(r'\b\w+\b', job_desc.lower()))

    # Clean and normalize resume keywords
    resume_keywords_set = set([k.strip().lower() for k in resume_keywords.split(',')])

    # Score based on keyword match (number of overlapping keywords)
    return len(job_keywords & resume_keywords_set)
