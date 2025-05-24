import requests
from bs4 import BeautifulSoup

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
