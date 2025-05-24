import requests
from bs4 import BeautifulSoup
import json
import requests
from bs4 import BeautifulSoup
from recipe_scrapers import scrape_me

def extract_jsonld_recipe(url, timeout=10):
    """
    Fetch the page and extract Schema.org JSON-LD Recipe data if present.
    Returns a dict {title, ingredients: [str], instructions: [str]} or None.
    """
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string)
        except (TypeError, json.JSONDecodeError):
            continue

        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            if entry.get("@type", "").lower() == "recipe":
                # Normalize instructions to a flat list of strings
                instrs = entry.get("recipeInstructions", [])
                steps = []
                for step in instrs:
                    if isinstance(step, dict) and "text" in step:
                        steps.append(step["text"])
                    elif isinstance(step, str):
                        steps.append(step)
                return {
                    "title": entry.get("name", ""),
                    "ingredients": entry.get("recipeIngredient", []),
                    "instructions": steps,
                    "image": entry.get("image"),
                    "yield": entry.get("recipeYield")
                }
    return None

def scrape_recipe(url):
    """
    Use recipe-scrapers as a fallback to pull title, ingredients, and instructions.
    Returns the same shape dict or None on failure.
    """
    try:
        scraper = scrape_me(url)
        instr = scraper.instructions()
        # often a single string with newlines
        instr_list = instr.split("\n") if instr else []
        return {
            "title": scraper.title() or "",
            "ingredients": scraper.ingredients() or [],
            "instructions": [step for step in instr_list if step.strip()]
        }
    except Exception:
        return None

def fetch_opengraph_metadata(url):
    try:
        response = requests.get(url, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')

        og_title = soup.find("meta", property="og:title")
        og_image = soup.find("meta", property="og:image")
        og_desc = soup.find("meta", property="og:description")

        return {
            "title": og_title["content"] if og_title else "",
            "image": og_image["content"] if og_image else "",
            "description": og_desc["content"] if og_desc else "",
            "url": url
        }
    except Exception as e:
        print(f"Failed to fetch OpenGraph data: {e}")
        return {"title": "", "image": "", "description": "", "url": url}
