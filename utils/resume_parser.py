import PyPDF2
import spacy

# Load English NLP model (make sure it's installed with: python -m spacy download en_core_web_sm)
nlp = spacy.load("en_core_web_sm")

def extract_keywords_from_pdf(filepath):
    text = ''
    try:
        with open(filepath, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                text += page.extract_text() or ""
    except Exception as e:
        print("Error reading PDF:", e)
        return ""

    doc = nlp(text)

    keywords = set()

    # Extract nouns and named entities
    for token in doc:
        if token.pos_ in ['NOUN', 'PROPN'] and len(token.text) > 3:
            keywords.add(token.lemma_.lower())

    for ent in doc.ents:
        if ent.label_ in ['ORG', 'PRODUCT', 'PERSON', 'WORK_OF_ART']:
            keywords.add(ent.text.lower())

    # Return a comma-separated list of the top 30 keywords
    return ', '.join(sorted(keywords)[:30])
