import spacy

# Load the spaCy language model
# For better accuracy, use "en_core_web_md" if installed
try:
    nlp = spacy.load("en_core_web_md")  # Better model (install with: python -m spacy download en_core_web_md)
except:
    nlp = spacy.load("en_core_web_sm")  # Fallback to small model

# Define soft skills / cultural fit traits
POSITIVE_TRAITS = [
    "teamwork", "collaboration", "communication", "leadership", "adaptability",
    "problem-solving", "creativity", "integrity", "innovation", "empathy"
]

def check_cultural_fit(text):
    """
    Analyzes resume text and calculates a cultural fit score based on the presence of soft skills.

    Parameters:
    - text (str): Full extracted resume text.

    Returns:
    - float: Score (0 to 100) based on percentage of matched traits.
    """
    if not text.strip():
        return 0.0

    doc = nlp(text.lower())
    matched_traits = set()

    # Use simple keyword matching for robustness
    for trait in POSITIVE_TRAITS:
        if trait in text.lower():
            matched_traits.add(trait)
            continue
        # Fallback to semantic similarity if not found as keyword
        trait_doc = nlp(trait)
        for sent in doc.sents:
            if trait_doc.similarity(sent) > 0.7:  # Semantic similarity threshold
                matched_traits.add(trait)
                break

    score = len(matched_traits) / len(POSITIVE_TRAITS) * 100
    return round(score, 2)
